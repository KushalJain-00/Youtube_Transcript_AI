from flask import Flask, request, jsonify, send_file, render_template, session
from flask_cors import CORS
import sqlite3, hashlib, os, re, io, time, json
from datetime import datetime, timedelta
from functools import wraps
import secrets

app = Flask(__name__)

# ─── PRODUCTION CONFIG ────────────────────────────────────────────────────────
# SECRET_KEY: Must be persistent across restarts or sessions will be invalidated.
# Set via environment variable in production. Falls back to random for local dev.
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("FLASK_ENV") == "production"
app.config["SESSION_COOKIE_HTTPONLY"] = True

CORS(app, supports_credentials=True)

DB_PATH = os.environ.get("DB_PATH", "ytai_data.db")

# ─── DB SETUP ────────────────────────────────────────────────────────────────

def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db

def init_db():
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            provider TEXT NOT NULL,
            key_value TEXT NOT NULL,
            label TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            title TEXT,
            url TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
    """)
    db.commit()
    db.close()

init_db()

# ─── AUTH HELPERS ─────────────────────────────────────────────────────────────

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "Not authenticated"}), 401
        return f(*args, **kwargs)
    return decorated

def get_user_api_key(user_id, provider):
    db = get_db()
    row = db.execute(
        "SELECT key_value FROM api_keys WHERE user_id=? AND provider=? ORDER BY id DESC LIMIT 1",
        (user_id, provider)
    ).fetchone()
    db.close()
    return row["key_value"] if row else None

# ─── AUTH ROUTES ──────────────────────────────────────────────────────────────

@app.route("/api/register", methods=["POST"])
def register():
    data = request.json
    username = data.get("username", "").strip()
    email = data.get("email", "").strip()
    password = data.get("password", "")
    if not username or not email or not password:
        return jsonify({"error": "All fields required"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400
    try:
        db = get_db()
        db.execute(
            "INSERT INTO users (username, email, password_hash) VALUES (?,?,?)",
            (username, email, hash_pw(password))
        )
        db.commit()
        user = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        db.close()
        return jsonify({"success": True, "username": username})
    except sqlite3.IntegrityError:
        return jsonify({"error": "Username or email already exists"}), 400

@app.route("/api/login", methods=["POST"])
def login():
    data = request.json
    username = data.get("username", "").strip()
    password = data.get("password", "")
    db = get_db()
    user = db.execute(
        "SELECT * FROM users WHERE (username=? OR email=?) AND password_hash=?",
        (username, username, hash_pw(password))
    ).fetchone()
    db.close()
    if not user:
        return jsonify({"error": "Invalid credentials"}), 401
    session["user_id"] = user["id"]
    session["username"] = user["username"]
    return jsonify({"success": True, "username": user["username"]})

@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"success": True})

@app.route("/api/me")
def me():
    if "user_id" not in session:
        return jsonify({"authenticated": False})
    return jsonify({"authenticated": True, "username": session["username"], "user_id": session["user_id"]})

# ─── API KEYS ─────────────────────────────────────────────────────────────────

@app.route("/api/keys", methods=["GET"])
@login_required
def get_keys():
    db = get_db()
    rows = db.execute(
        "SELECT id, provider, label, key_value, created_at FROM api_keys WHERE user_id=? ORDER BY provider",
        (session["user_id"],)
    ).fetchall()
    db.close()
    keys = []
    for r in rows:
        kv = r["key_value"]
        masked = kv[:6] + "..." + kv[-4:] if len(kv) > 12 else "****"
        keys.append({"id": r["id"], "provider": r["provider"], "label": r["label"], "masked": masked, "created_at": r["created_at"]})
    return jsonify(keys)

@app.route("/api/keys", methods=["POST"])
@login_required
def save_key():
    data = request.json
    provider = data.get("provider", "").strip()
    key_value = data.get("key_value", "").strip()
    label = data.get("label", "").strip()
    if not provider or not key_value:
        return jsonify({"error": "Provider and key required"}), 400
    db = get_db()
    # Delete existing key for this provider
    db.execute("DELETE FROM api_keys WHERE user_id=? AND provider=?", (session["user_id"], provider))
    db.execute(
        "INSERT INTO api_keys (user_id, provider, key_value, label) VALUES (?,?,?,?)",
        (session["user_id"], provider, key_value, label or provider)
    )
    db.commit()
    db.close()
    return jsonify({"success": True})

@app.route("/api/keys/<int:key_id>", methods=["DELETE"])
@login_required
def delete_key(key_id):
    db = get_db()
    db.execute("DELETE FROM api_keys WHERE id=? AND user_id=?", (key_id, session["user_id"]))
    db.commit()
    db.close()
    return jsonify({"success": True})

# ─── HISTORY ─────────────────────────────────────────────────────────────────

@app.route("/api/history")
@login_required
def get_history():
    db = get_db()
    rows = db.execute(
        "SELECT * FROM history WHERE user_id=? ORDER BY created_at DESC LIMIT 50",
        (session["user_id"],)
    ).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

def save_history(user_id, type_, title, url=None):
    db = get_db()
    db.execute(
        "INSERT INTO history (user_id, type, title, url) VALUES (?,?,?,?)",
        (user_id, type_, title, url)
    )
    db.commit()
    db.close()

# ─── TRANSCRIPT ──────────────────────────────────────────────────────────────

def extract_video_id(url):
    patterns = [
        r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
        r'(?:embed\/)([0-9A-Za-z_-]{11})',
        r'(?:youtu\.be\/)([0-9A-Za-z_-]{11})',
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None

def get_video_info(video_id):
    import requests as req
    try:
        r = req.get(f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json", timeout=10)
        if r.status_code == 200:
            d = r.json()
            return {"title": d.get("title","Unknown"), "channel": d.get("author_name","Unknown"), "url": f"https://www.youtube.com/watch?v={video_id}"}
    except:
        pass
    return {"title": "Unknown", "channel": "Unknown", "url": f"https://www.youtube.com/watch?v={video_id}"}

def get_transcript(video_id):
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound
        api = YouTubeTranscriptApi()
        tl = api.list(video_id)
        try:
            t = tl.find_transcript(["en"])
            fetched = t.fetch()
            return fetched, "en", t.is_generated
        except:
            pass
        for t in tl:
            fetched = t.fetch()
            return fetched, t.language_code, t.is_generated
        return None, None, "No transcripts"
    except Exception as e:
        return None, None, str(e)

def format_transcript(data):
    lines = []
    for e in data:
        start = getattr(e, "start", 0) if hasattr(e, "start") else e.get("start", 0)
        text = getattr(e, "text", "") if hasattr(e, "text") else e.get("text", "")
        m, s = int(start // 60), int(start % 60)
        lines.append(f"[{m:02d}:{s:02d}] {text}")
    return "\n".join(lines)

def plain_transcript(data):
    texts = []
    for e in data:
        text = getattr(e, "text", "") if hasattr(e, "text") else e.get("text", "")
        texts.append(text)
    return " ".join(texts)

# ─── AI SUMMARY ──────────────────────────────────────────────────────────────

def build_ai_client(provider, api_key):
    if provider == "openai":
        from openai import OpenAI
        return OpenAI(api_key=api_key), "gpt-4o"
    elif provider == "anthropic":
        import anthropic
        return anthropic, api_key  # handled separately
    elif provider == "gemini":
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        return genai, "gemini-1.5-flash"
    raise ValueError(f"Unknown provider: {provider}")

def call_ai(provider, api_key, prompt):
    if provider == "openai":
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4000
        )
        return resp.choices[0].message.content
    elif provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}]
        )
        return msg.content[0].text
    elif provider == "gemini":
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        resp = model.generate_content(prompt)
        return resp.text
    raise ValueError(f"Unknown provider: {provider}")

SUMMARY_PROMPT = """You are an expert educational content summarizer.

Transcript:
---
{text}
---

Provide structured output in EXACTLY this format (keep section headers):

SUMMARY:
[2-3 paragraph summary of the content]

KEY TAKEAWAYS:
1. [First key point]
2. [Second key point]
3. [Third key point]
4. [Fourth key point]
5. [Fifth key point]

STUDY NOTES:
- [Note 1]
- [Note 2]
- [Note 3]
- [Note 4]
- [Note 5]
"""

def parse_ai_response(text):
    sections = {"summary": "", "takeaways": [], "study_notes": []}
    current = None
    buf = []

    def flush():
        if current == "summary":
            sections["summary"] = "\n".join(buf).strip()
        elif current == "takeaways":
            sections["takeaways"] = [re.sub(r"^\d+[\.\)]\s*","",l).strip() for l in buf if l.strip()]
        elif current == "study_notes":
            sections["study_notes"] = [re.sub(r"^[-•*]\s*","",l).strip() for l in buf if l.strip()]

    for line in text.split("\n"):
        up = line.strip().upper()
        if "SUMMARY:" in up:
            flush(); current = "summary"; buf = []
        elif "KEY TAKEAWAYS:" in up:
            flush(); current = "takeaways"; buf = []
        elif "STUDY NOTES:" in up:
            flush(); current = "study_notes"; buf = []
        else:
            if current: buf.append(line)
    flush()
    return sections

# ─── PDF GENERATION ──────────────────────────────────────────────────────────

def generate_pdf(sections, video_info, transcript_text, word_count):
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, HRFlowable
    from reportlab.lib.units import inch
    from reportlab.lib import colors

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter,
                            leftMargin=0.8*inch, rightMargin=0.8*inch,
                            topMargin=0.8*inch, bottomMargin=0.8*inch)
    styles = getSampleStyleSheet()

    def S(name, **kw):
        return ParagraphStyle(name, parent=styles["Normal"], **kw)

    title_s = S("T", fontSize=22, textColor=colors.HexColor("#0f172a"), spaceAfter=6, alignment=1, fontName="Helvetica-Bold")
    sub_s = S("Sub", fontSize=10, textColor=colors.HexColor("#64748b"), spaceAfter=4, alignment=1)
    head_s = S("H", fontSize=13, textColor=colors.HexColor("#1e40af"), spaceBefore=16, spaceAfter=6, fontName="Helvetica-Bold")
    body_s = S("B", fontSize=10, textColor=colors.HexColor("#1e293b"), leading=15, spaceAfter=4)
    bullet_s = S("Bl", fontSize=10, textColor=colors.HexColor("#374151"), leading=14, leftIndent=14, spaceAfter=3)
    trans_s = S("Tr", fontSize=9, textColor=colors.HexColor("#6b7280"), leading=13, spaceAfter=6)

    def safe(t):
        return (t or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

    story = []
    story.append(Paragraph("AI YouTube Learner", title_s))
    story.append(Paragraph("Transcript & AI Summary Report", sub_s))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2e8f0"), spaceAfter=12))

    if video_info:
        story.append(Paragraph(safe(video_info.get("title","")), S("VT", fontSize=14, textColor=colors.HexColor("#0f172a"), alignment=1, spaceAfter=4, fontName="Helvetica-Bold")))
        story.append(Paragraph(f"Channel: {safe(video_info.get('channel',''))}", sub_s))
        url = video_info.get("url","")
        if url:
            story.append(Paragraph(f'<a href="{url}" color="#1d4ed8">{url}</a>', sub_s))
    story.append(Paragraph(f"Words: {word_count:,} | Generated: {datetime.now().strftime('%d %b %Y %H:%M')}", sub_s))
    story.append(Spacer(1, 0.2*inch))

    if sections.get("summary"):
        story.append(Paragraph("Summary", head_s))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#bfdbfe"), spaceAfter=8))
        story.append(Paragraph(safe(sections["summary"]), body_s))

    if sections.get("takeaways"):
        story.append(Paragraph("Key Takeaways", head_s))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#bfdbfe"), spaceAfter=8))
        for i, t in enumerate(sections["takeaways"][:5], 1):
            story.append(Paragraph(f"{i}. {safe(t)}", bullet_s))

    if sections.get("study_notes"):
        story.append(Paragraph("Study Notes", head_s))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#bfdbfe"), spaceAfter=8))
        for n in sections["study_notes"]:
            story.append(Paragraph(f"• {safe(n)}", bullet_s))

    story.append(PageBreak())
    story.append(Paragraph("Full Transcript", head_s))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#bfdbfe"), spaceAfter=8))
    for line in (transcript_text or "").split("\n"):
        if line.strip():
            story.append(Paragraph(safe(line), trans_s))

    doc.build(story)
    buf.seek(0)
    return buf.getvalue()

# ─── MAIN API ─────────────────────────────────────────────────────────────────

@app.route("/api/process-video", methods=["POST"])
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

    api_key = get_user_api_key(session["user_id"], provider)
    if not api_key and not skip_ai:
        return jsonify({"error": f"No API key saved for {provider}. Add one in Settings."}), 400

    # Transcript
    transcript_data, lang, is_gen = get_transcript(video_id)
    if transcript_data is None:
        return jsonify({"error": f"Could not get transcript: {lang}"}), 400

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
            ai_text = call_ai(provider, api_key, prompt)
            result["sections"] = parse_ai_response(ai_text)
        except Exception as e:
            result["ai_error"] = str(e)

    save_history(session["user_id"], "video", video_info["title"], url)
    return jsonify(result)

@app.route("/api/download-pdf", methods=["POST"])
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

@app.route("/api/process-channel", methods=["POST"])
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
    if gen_summaries:
        api_key = get_user_api_key(session["user_id"], provider)
        if not api_key:
            return jsonify({"error": f"No API key for {provider}"}), 400

    try:
        import yt_dlp
        from youtube_transcript_api import YouTubeTranscriptApi
        from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound

        url = channel_url.strip().rstrip("/")
        if not any(url.endswith(t) for t in ["/videos","/shorts","/live"]):
            url += "/videos"

        ydl_opts = {"quiet": True, "no_warnings": True, "extract_flat": True, "skip_unavailable_videos": True, "ignoreerrors": True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        if not info:
            return jsonify({"error": "Could not fetch channel"}), 400

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

        # Get transcripts
        api = YouTubeTranscriptApi()
        for v in videos:
            try:
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
            time.sleep(0.3)

        if gen_summaries and api_key:
            for v in videos:
                if not v.get("has_transcript"): continue
                try:
                    prompt = SUMMARY_PROMPT.format(text=v["transcript"][:6000])
                    ai = call_ai(provider, api_key, prompt)
                    parsed = parse_ai_response(ai)
                    v["ai_summary"] = parsed.get("summary","")
                    v["ai_takeaways"] = parsed.get("takeaways",[])
                except:
                    v["ai_summary"] = ""; v["ai_takeaways"] = []

        save_history(session["user_id"], "channel", channel_name, channel_url)
        return jsonify({"channel_name": channel_name, "videos": videos})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/download-channel-pdf", methods=["POST"])
@login_required
def download_channel_pdf():
    data = request.json
    videos = data.get("videos", [])
    channel_name = data.get("channel_name", "Channel")

    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, HRFlowable
    from reportlab.lib.units import inch
    from reportlab.lib import colors

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=0.8*inch, rightMargin=0.8*inch,
                            topMargin=0.8*inch, bottomMargin=0.8*inch)
    styles = getSampleStyleSheet()
    def S(n, **kw): return ParagraphStyle(n, parent=styles["Normal"], **kw)
    def safe(t): return (t or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

    title_s = S("T", fontSize=20, textColor=colors.HexColor("#0f172a"), alignment=1, spaceAfter=6, fontName="Helvetica-Bold")
    sub_s = S("Su", fontSize=10, textColor=colors.HexColor("#64748b"), alignment=1, spaceAfter=4)
    vt_s = S("VT", fontSize=13, textColor=colors.HexColor("#1e40af"), spaceBefore=12, spaceAfter=4, fontName="Helvetica-Bold")
    body_s = S("B", fontSize=10, textColor=colors.HexColor("#1e293b"), leading=14, spaceAfter=4)
    bullet_s = S("Bl", fontSize=10, textColor=colors.HexColor("#374151"), leading=13, leftIndent=12, spaceAfter=2)
    trans_s = S("Tr", fontSize=9, textColor=colors.HexColor("#6b7280"), leading=12, spaceAfter=4)

    story = []
    story.append(Paragraph("YouTube Channel Report", title_s))
    story.append(Paragraph(safe(channel_name), S("CN", fontSize=14, textColor=colors.HexColor("#1e40af"), alignment=1, spaceAfter=4)))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%d %b %Y')} | Videos: {len(videos)}", sub_s))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2e8f0"), spaceAfter=16))

    for i, v in enumerate(videos, 1):
        story.append(Paragraph(f"{i}. {safe(v.get('title','')[:80])}", vt_s))
        if v.get("url"):
            story.append(Paragraph(f'<a href="{v["url"]}" color="#1d4ed8">{v["url"]}</a>', S("U", fontSize=9, textColor=colors.HexColor("#6b7280"), spaceAfter=4)))

        if v.get("ai_summary"):
            story.append(Paragraph("Summary", S("SH", fontSize=10, fontName="Helvetica-Bold", textColor=colors.HexColor("#0f172a"), spaceAfter=2, spaceBefore=6)))
            story.append(Paragraph(safe(v["ai_summary"]), body_s))
        if v.get("ai_takeaways"):
            story.append(Paragraph("Key Points", S("KH", fontSize=10, fontName="Helvetica-Bold", textColor=colors.HexColor("#0f172a"), spaceAfter=2, spaceBefore=4)))
            for t in v["ai_takeaways"][:5]:
                story.append(Paragraph(f"• {safe(t)}", bullet_s))

        if v.get("transcript"):
            story.append(Paragraph("Transcript", S("TH", fontSize=10, fontName="Helvetica-Bold", textColor=colors.HexColor("#0f172a"), spaceAfter=2, spaceBefore=6)))
            snippet = v["transcript"][:1500]
            story.append(Paragraph(safe(snippet) + ("..." if len(v["transcript"]) > 1500 else ""), trans_s))

        if i < len(videos):
            story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e2e8f0"), spaceBefore=12, spaceAfter=4))

    doc.build(story)
    buf.seek(0)
    safe_name = re.sub(r"[^\w\s-]","",channel_name).strip().replace(" ","_")
    return send_file(io.BytesIO(buf.read()), mimetype="application/pdf", as_attachment=True,
                     download_name=f"{safe_name}_report.pdf")

@app.route("/")
def index():
    return render_template("index.html")

# ─── HEALTH CHECK (for hosting platforms) ─────────────────────────────────────
@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
