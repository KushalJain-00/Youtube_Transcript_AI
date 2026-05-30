import re

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
    except TranscriptsDisabled:
        return None, None, "Subtitles are disabled for this video by the creator."
    except NoTranscriptFound:
        return None, None, "No English transcript was found for this video."
    except Exception as e:
        return None, None, str(e)

def format_transcript(data):
    lines = []
    for e in data:
        start = getattr(e, "start", 0) if hasattr(e, "start") else e.get("start", 0)
        text = getattr(e, "text", "") if hasattr(e, "text") else e.get("text", "")
        m, s = int(start // 60), int(start % 60)
        lines.append(f"[{m:02d}:{s:02d}] {text}")
    return "\\n".join(lines)

def plain_transcript(data):
    texts = []
    for e in data:
        text = getattr(e, "text", "") if hasattr(e, "text") else e.get("text", "")
        texts.append(text)
    return " ".join(texts)
