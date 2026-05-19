# YT.AI — YouTube Intelligence Platform

Fetch YouTube transcripts and generate AI-powered summaries in PDF format.  
Local-first: all data stored in `ytai_data.db` (SQLite) — never deleted, never sent anywhere.

---

## Features

- **User accounts** — Register/login, each user has their own data
- **Single Video** — Fetch transcript + AI summary (Summary, Key Takeaways, Study Notes) → download as PDF
- **Channel Scraper** — Bulk scrape all videos from a channel, optional AI summaries per video → full PDF report
- **Multi-provider AI** — OpenAI (GPT-4o), Anthropic (Claude), Google Gemini — user configures their own keys
- **API Key Manager** — Save/delete keys per provider, securely stored in local SQLite
- **History** — All processed videos/channels logged per user

---

## Local Development

### Windows
Double-click `start.bat`

### Mac / Linux
```bash
chmod +x start.sh
./start.sh
```

Then open **http://localhost:5000** in your browser.

---

## First Time

1. Click **Register** and create an account
2. Go to **Settings** tab → add your API key for OpenAI, Anthropic, or Gemini
3. Use **Video** or **Channel** tab — select your provider, paste URL, click Process

---

## Deploy to Render (Recommended)

### Quick Deploy

1. Push this repo to GitHub
2. Go to [render.com](https://render.com) → **New** → **Blueprint**
3. Connect your GitHub repo — Render auto-detects `render.yaml`
4. Click **Apply** — done! `SECRET_KEY` is auto-generated

That's it. Render will install dependencies, start gunicorn, and give you a public URL.

### What You Get on Free Tier

- ✅ No request timeout — AI calls can take as long as needed
- ✅ SQLite works — data persists while the instance is running
- ✅ Auto-deploy on every `git push`
- ⚠️ Instance sleeps after 15 min of inactivity (~30s cold start)
- ⚠️ DB resets on redeploy (re-register + re-add API keys)

### Alternative: Self-Host / VPS

```bash
git clone <your-repo-url> && cd Youtube_Transcript_AI
pip install -r requirements.txt

export SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
export FLASK_ENV=production
export PORT=8000

gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120
```

### Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `SECRET_KEY` | **Yes** (prod) | Random | Session encryption key — must persist |
| `PORT` | No | `5000` | Server port |
| `FLASK_ENV` | No | `development` | Set to `production` for secure cookies |
| `FLASK_DEBUG` | No | `0` | Set to `1` for debug mode (dev only) |
| `DB_PATH` | No | `ytai_data.db` | SQLite database file path |

---

## Data Storage

All data lives in `ytai_data.db` (same folder as `app.py`).  
**Never delete this file** — it contains all user accounts, API keys, and history.

To back up: copy `ytai_data.db` anywhere.

---

## AI Provider Keys

| Provider | Where to get |
|---|---|
| OpenAI | platform.openai.com → API Keys |
| Anthropic | console.anthropic.com → API Keys |
| Google Gemini | aistudio.google.com → Get API Key |

---

## Project Structure

```
Youtube_Transcript_AI/
├── app.py              # Flask application (all routes + logic)
├── requirements.txt    # Python dependencies
├── Procfile            # WSGI entry point for gunicorn
├── render.yaml         # Render.com auto-deploy blueprint
├── runtime.txt         # Python version specification
├── .env.example        # Environment variable reference
├── .gitignore          # Files excluded from git
├── start.bat           # Windows local launcher
├── start.sh            # Linux/Mac local launcher
├── templates/
│   └── index.html      # Full SPA frontend
└── static/             # Static assets
```

---

## Requirements

- Python 3.9+
- Internet connection (for YouTube and AI APIs)
