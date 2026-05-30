from flask import Flask, render_template
from flask_cors import CORS
import os
import secrets
import logging
from database import init_db

logging.basicConfig(level=logging.INFO)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static"))

# ─── PRODUCTION CONFIG ────────────────────────────────────────────────────────
secret_key_path = os.path.join(BASE_DIR, ".secret_key")
if "SECRET_KEY" in os.environ:
    app.secret_key = os.environ["SECRET_KEY"]
else:
    if os.path.exists(secret_key_path):
        with open(secret_key_path, "r") as f:
            app.secret_key = f.read().strip()
    else:
        app.secret_key = secrets.token_hex(32)
        try:
            with open(secret_key_path, "w") as f:
                f.write(app.secret_key)
        except Exception:
            pass

app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("FLASK_ENV") == "production"
app.config["SESSION_COOKIE_HTTPONLY"] = True

CORS(app, supports_credentials=True)

# ─── RATE LIMITING ───────────────────────────────────────────────────────────
try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    limiter = Limiter(
        get_remote_address,
        app=app,
        default_limits=["200 per hour"],
        storage_uri="memory://",
    )
except ImportError:
    limiter = None

# ─── INIT DB ─────────────────────────────────────────────────────────────────
init_db()

# ─── BLUEPRINTS ──────────────────────────────────────────────────────────────
from routes.auth import auth_bp
from routes.api import api_bp

app.register_blueprint(auth_bp)
app.register_blueprint(api_bp)

# Apply rate limits to heavy routes if limiter is available
if limiter:
    limiter.limit("10 per minute")(app.view_functions["api.process_video"])
    limiter.limit("5 per minute")(app.view_functions["api.process_channel"])

# ─── MAIN ROUTE ──────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV") != "production"
    app.run(host="0.0.0.0", port=port, debug=debug)
