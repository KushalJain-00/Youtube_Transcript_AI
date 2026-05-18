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

## Deploy to Production

### Option A: Render (Recommended — Free Tier)

1. Push this repo to GitHub
2. Go to [render.com](https://render.com) → **New** → **Blueprint**
3. Connect your GitHub repo — Render auto-detects `render.yaml`
4. Click **Apply** — done! `SECRET_KEY` is auto-generated

### Option B: Railway

1. Push to GitHub
2. Go to [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub**
3. Set environment variables:
   - `SECRET_KEY` — run `python -c "import secrets; print(secrets.token_hex(32))"`
   - `FLASK_ENV` = `production`
4. Railway auto-detects `Procfile`

### Option C: Manual / VPS

```bash
# Clone and install
git clone <your-repo-url> && cd Youtube_Transcript_AI
pip install -r requirements.txt

# Set environment
export SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
export FLASK_ENV=production
export PORT=8000

# Run with gunicorn
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
├── Procfile            # WSGI entry point for hosting platforms
├── render.yaml         # Render.com auto-deploy blueprint
├── runtime.txt         # Python version specification
├── .env.example        # Environment variable reference
├── .gitignore          # Files excluded from git
├── start.bat           # Windows local launcher
├── start.sh            # Linux/Mac local launcher
├── templates/
│   └── index.html      # Full SPA frontend
└── static/             # Static assets (currently unused)
```

---

## Requirements

- Python 3.9+
- Internet connection (for YouTube and AI APIs)
