from flask import Blueprint, request, jsonify, send_file, session, Response
import io
import time
import json
import logging
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor, as_completed
from utils import login_required, get_user_api_key, save_history, encrypt_key
from database import get_db
from services.youtube_service import extract_video_id, get_video_info, get_transcript, format_transcript, plain_transcript
from services.ai_service import call_ai, parse_ai_response, SUMMARY_PROMPT
from services.pdf_service import generate_pdf
import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi

logger = logging.getLogger(__name__)

api_bp = Blueprint("api", __name__)

# ─── OPENROUTER MODEL CACHE ─────────────────────────────────────────────────
_openrouter_cache = {"models": None, "ts": 0}
_OPENROUTER_CACHE_TTL = 3600  # 1 hour

def _get_openrouter_models():
    now = time.time()
    if _openrouter_cache["models"] and (now - _openrouter_cache["ts"]) < _OPENROUTER_CACHE_TTL:
        return _openrouter_cache["models"]
    try:
        import requests
        r = requests.get("https://openrouter.ai/api/v1/models", timeout=10)
        data = r.json().get("data", [])
        free_models = []
        for m in data:
            pricing = m.get("pricing", {})
            if pricing.get("prompt") == "0" and pricing.get("completion") == "0":
                free_models.append(m["id"])
        _openrouter_cache["models"] = free_models
        _openrouter_cache["ts"] = now
        return free_models
    except Exception:
        return _openrouter_cache["models"] or ["openrouter/auto", "google/gemini-2.0-flash:free", "meta-llama/llama-3.3-70b-instruct:free"]


@api_bp.route("/api/models/<provider>")
def get_models(provider):
    models = {
        "openai": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo", "o3-mini"],
        "anthropic": ["claude-3-7-sonnet-20250219", "claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022", "claude-3-opus-20240229"],
        "gemini": ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"],
        "groq": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768", "gemma2-9b-it"],
        "deepseek": ["deepseek-chat", "deepseek-reasoner"],
        "ollama": ["llama3.2", "llama3.1", "mistral", "codellama", "phi3", "gemma2", "qwen2.5"]
    }
    if provider == "openrouter":
        return jsonify(_get_openrouter_models())
    return jsonify(models.get(provider, []))


# ─── VIDEO CACHE HELPERS ────────────────────────────────────────────────────

def _get_cached_video(video_id, provider, model):
    """Check if we have a cached AI summary for this video+provider+model combo."""
    db = get_db()
    row = db.execute(
        "SELECT transcript, ai_summary, ai_takeaways FROM video_cache WHERE video_id=? AND provider=? AND model=?",
        (video_id, provider or "", model or "")
    ).fetchone()
    db.close()
    if row:
        return {
            "transcript": row["transcript"],
            "ai_summary": row["ai_summary"],
            "ai_takeaways": row["ai_takeaways"]
        }
    return None

def _save_video_cache(video_id, transcript, ai_summary, ai_takeaways, provider, model):
    try:
        db = get_db()
        db.execute(
            "INSERT OR REPLACE INTO video_cache (video_id, transcript, ai_summary, ai_takeaways, provider, model) VALUES (?,?,?,?,?,?)",
            (video_id, transcript, ai_summary, json.dumps(ai_takeaways) if isinstance(ai_takeaways, list) else ai_takeaways, provider or "", model or "")
        )
        db.commit()
        db.close()
    except Exception as e:
        logger.warning(f"Cache write failed: {e}")


# ─── API KEY ROUTES ──────────────────────────────────────────────────────────

@api_bp.route("/api/keys", methods=["GET"])
@login_required
def get_keys():
    db = get_db()
    rows = db.execute(
        "SELECT id, provider, label, key_value, model, created_at FROM api_keys WHERE user_id=? ORDER BY provider",
        (session["user_id"],)
    ).fetchall()
    db.close()
    keys = []
    for r in rows:
        kv = r["key_value"]
        # Show first 6 and last 4 chars of the original key for display
        masked = kv[:6] + "..." + kv[-4:] if len(kv) > 12 else "****"
        keys.append({"id": r["id"], "provider": r["provider"], "label": r["label"], "model": r["model"], "masked": masked, "created_at": r["created_at"]})
    return jsonify(keys)

@api_bp.route("/api/keys", methods=["POST"])
@login_required
def save_key():
    data = request.json
    provider = data.get("provider", "").strip()
    key_value = data.get("key_value", "").strip()
    label = data.get("label", "").strip()
    model = data.get("model", "").strip()
    if not provider or not key_value:
        return jsonify({"error": "Provider and key required"}), 400
    db = get_db()
    db.execute("DELETE FROM api_keys WHERE user_id=? AND provider=?", (session["user_id"], provider))
    db.execute(
        "INSERT INTO api_keys (user_id, provider, key_value, label, model) VALUES (?,?,?,?,?)",
        (session["user_id"], provider, encrypt_key(key_value), label or provider, model)
    )
    db.commit()
    db.close()
    return jsonify({"success": True})

@api_bp.route("/api/keys/<int:key_id>", methods=["DELETE"])
@login_required
def delete_key(key_id):
    db = get_db()
    db.execute("DELETE FROM api_keys WHERE id=? AND user_id=?", (key_id, session["user_id"]))
    db.commit()
    db.close()
    return jsonify({"success": True})

# ─── HISTORY ─────────────────────────────────────────────────────────────────

@api_bp.route("/api/history")
@login_required
def get_history():
    db = get_db()
    rows = db.execute(
        "SELECT * FROM history WHERE user_id=? ORDER BY created_at DESC LIMIT 50",
        (session["user_id"],)
    ).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

# ─── PROCESS VIDEO (WITH CACHE) ─────────────────────────────────────────────

@api_bp.route("/api/process-video", methods=["POST"])
@login_required
def process_video():
    data = request.json
    url = data.get("url","").strip()
    provider = data.get("provider","openai")
    skip_ai = data.get("skip_ai", False)

    if not url:
        return jsonify({"error": "URL required"}), 400

    video_id = extract_video_id(url)
    if not video_id:
        return jsonify({"error": "Invalid YouTube URL"}), 400

    api_key, model_name = get_user_api_key(session["user_id"], provider)
    if provider == "ollama":
        api_key = "ollama"
    if not api_key and not skip_ai:
        return jsonify({"error": f"No API key saved for {provider}. Add one in Settings."}), 400

    # Check cache first
    if not skip_ai:
        cached = _get_cached_video(video_id, provider, model_name)
        if cached and cached.get("ai_summary"):
            video_info = get_video_info(video_id)
            takeaways = cached["ai_takeaways"]
            if isinstance(takeaways, str):
                try: takeaways = json.loads(takeaways)
                except: takeaways = []
            result = {
                "video_id": video_id,
                "video_info": video_info,
                "transcript": cached["transcript"],
                "word_count": len((cached["transcript"] or "").split()),
                "lang": "en",
                "is_generated": False,
                "sections": {
                    "summary": cached["ai_summary"],
                    "takeaways": takeaways,
                    "study_notes": []
                },
                "cached": True
            }
            save_history(session["user_id"], "video", video_info["title"], url)
            return jsonify(result)

    transcript_data, lang, is_gen = get_transcript(video_id)
    if transcript_data is None:
        return jsonify({"error": f"Could not get transcript: {is_gen}"}), 400

    formatted = format_transcript(transcript_data)
    plain = plain_transcript(transcript_data)
    word_count = len(plain.split())
    video_info = get_video_info(video_id)

    result = {
        "video_id": video_id,
        "video_info": video_info,
        "transcript": formatted,
        "word_count": word_count,
        "lang": lang,
        "is_generated": is_gen,
        "sections": None
    }

    if not skip_ai and api_key:
        try:
            prompt = SUMMARY_PROMPT.format(text=plain[:8000])
            ai_text = call_ai(provider, api_key, model_name, prompt)
            sections = parse_ai_response(ai_text)
            result["sections"] = sections
            # Save to cache
            _save_video_cache(
                video_id, formatted,
                sections.get("summary", ""),
                sections.get("takeaways", []),
                provider, model_name
            )
        except Exception as e:
            logger.error(f"AI call failed: {e}")
            result["ai_error"] = str(e)

    save_history(session["user_id"], "video", video_info["title"], url)
    return jsonify(result)

# ─── DOWNLOAD PDF ────────────────────────────────────────────────────────────

@api_bp.route("/api/download-pdf", methods=["POST"])
@login_required
def download_pdf():
    data = request.json
    sections = data.get("sections", {})
    video_info = data.get("video_info", {})
    transcript = data.get("transcript", "")
    word_count = data.get("word_count", 0)

    try:
        pdf_bytes = generate_pdf(sections, video_info, transcript, word_count)
        vid_id = data.get("video_id", "video")
        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"summary_{vid_id}.pdf"
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ─── PROCESS CHANNEL (SSE + PARALLEL) ───────────────────────────────────────

@api_bp.route("/api/process-channel", methods=["POST"])
@login_required
def process_channel():
    data = request.json
    channel_url = data.get("url","").strip()
    max_videos = min(int(data.get("max_videos", 20)), 100)
    provider = data.get("provider","openai")
    gen_summaries = data.get("gen_summaries", False)

    if not channel_url:
        return jsonify({"error": "Channel URL required"}), 400

    api_key = None
    model_name = None
    if gen_summaries:
        api_key, model_name = get_user_api_key(session["user_id"], provider)
        if provider == "ollama":
            api_key = "ollama"
        if not api_key:
            return jsonify({"error": f"No API key for {provider}"}), 400

    user_id = session["user_id"]

    def generate():
        try:
            url = channel_url.strip().rstrip("/")
            if not any(url.endswith(t) for t in ["/videos","/shorts","/live"]):
                url += "/videos"

            yield f"data: {json.dumps({'progress': 10, 'text': 'Fetching channel info...'})}\n\n"

            ydl_opts = {"quiet": True, "no_warnings": True, "extract_flat": True, "skip_unavailable_videos": True, "ignoreerrors": True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

            if not info:
                yield f"data: {json.dumps({'error': 'Could not fetch channel'})}\n\n"
                return

            channel_name = info.get("title","Unknown Channel")
            entries = info.get("entries",[]) or []

            videos = []
            for e in entries:
                if not e: continue
                if len(videos) >= max_videos: break
                vid_id = e.get("id","")
                if len(vid_id) == 11:
                    videos.append({"video_id": vid_id, "title": e.get("title","Untitled"),
                                   "url": f"https://www.youtube.com/watch?v={vid_id}",
                                   "duration": e.get("duration"), "upload_date": e.get("upload_date")})

            yield f"data: {json.dumps({'progress': 30, 'text': f'Found {len(videos)} videos, fetching transcripts...'})}\n\n"

            # Parallel transcript fetching
            def fetch_transcript(v):
                try:
                    api = YouTubeTranscriptApi()
                    tl = api.list(v["video_id"])
                    try: t = tl.find_transcript(["en"])
                    except: t = next(iter(tl), None)
                    if t:
                        fetched = t.fetch()
                        v["transcript"] = " ".join(
                            (getattr(e,"text","") if hasattr(e,"text") else e.get("text","")) for e in fetched
                        )
                        v["has_transcript"] = True
                    else:
                        v["transcript"] = ""; v["has_transcript"] = False
                except:
                    v["transcript"] = ""; v["has_transcript"] = False

            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = {executor.submit(fetch_transcript, v): v for v in videos}
                done_count = 0
                for future in as_completed(futures):
                    done_count += 1
                    progress = 30 + int(40 * done_count / max(1, len(videos)))
                    yield f"data: {json.dumps({'progress': progress, 'text': f'Fetched transcript {done_count}/{len(videos)}'})}\n\n"

            if gen_summaries and (api_key or provider == "ollama"):
                yield f"data: {json.dumps({'progress': 70, 'text': 'Generating AI summaries (parallel)...'})}\n\n"
                def process_ai(v):
                    if not v.get("has_transcript"): return
                    try:
                        prompt = SUMMARY_PROMPT.format(text=v["transcript"][:6000])
                        ai = call_ai(provider, api_key, model_name, prompt)
                        parsed = parse_ai_response(ai)
                        v["ai_summary"] = parsed.get("summary","")
                        v["ai_takeaways"] = parsed.get("takeaways",[])
                    except:
                        v["ai_summary"] = ""; v["ai_takeaways"] = []

                tasks = [v for v in videos if v.get("has_transcript")]
                completed = 0
                with ThreadPoolExecutor(max_workers=5) as executor:
                    futures = {executor.submit(process_ai, v): v for v in tasks}
                    for future in as_completed(futures):
                        completed += 1
                        progress = 70 + int(25 * completed / max(1, len(tasks)))
                        yield f"data: {json.dumps({'progress': progress, 'text': f'AI Summary {completed}/{len(tasks)}'})}\n\n"

            yield f"data: {json.dumps({'progress': 99, 'text': 'Saving history...'})}\n\n"
            try:
                save_history(user_id, "channel", channel_name, channel_url)
            except Exception:
                pass

            yield f"data: {json.dumps({'progress': 100, 'text': 'Done', 'channel_name': channel_name, 'videos': videos})}\n\n"
        except Exception as e:
            logger.error(f"Channel processing error: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(generate(), mimetype='text/event-stream')
