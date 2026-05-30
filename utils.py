from flask import session, jsonify
from functools import wraps
from database import get_db
import os
import logging

logger = logging.getLogger(__name__)

# ─── FERNET ENCRYPTION FOR API KEYS ─────────────────────────────────────────
try:
    from cryptography.fernet import Fernet

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    _fernet_key_path = os.path.join(BASE_DIR, ".fernet_key")

    if os.path.exists(_fernet_key_path):
        with open(_fernet_key_path, "rb") as f:
            _FERNET_KEY = f.read().strip()
    else:
        _FERNET_KEY = Fernet.generate_key()
        try:
            with open(_fernet_key_path, "wb") as f:
                f.write(_FERNET_KEY)
        except Exception:
            pass

    _fernet = Fernet(_FERNET_KEY)

    def encrypt_key(plaintext):
        return _fernet.encrypt(plaintext.encode()).decode()

    def decrypt_key(ciphertext):
        try:
            return _fernet.decrypt(ciphertext.encode()).decode()
        except Exception:
            # Fallback: key was stored before encryption was added
            return ciphertext
except ImportError:
    logger.warning("cryptography not installed — API keys will NOT be encrypted at rest.")
    def encrypt_key(plaintext):
        return plaintext
    def decrypt_key(ciphertext):
        return ciphertext

# ─── DECORATORS ──────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "Not authenticated"}), 401
        return f(*args, **kwargs)
    return decorated

# ─── HELPERS ─────────────────────────────────────────────────────────────────

def get_user_api_key(user_id, provider):
    db = get_db()
    row = db.execute(
        "SELECT key_value, model FROM api_keys WHERE user_id=? AND provider=? ORDER BY id DESC LIMIT 1",
        (user_id, provider)
    ).fetchone()
    db.close()
    if row:
        return decrypt_key(row["key_value"]), row["model"]
    return None, None

def save_history(user_id, type_, title, url=None):
    db = get_db()
    db.execute(
        "INSERT INTO history (user_id, type, title, url) VALUES (?,?,?,?)",
        (user_id, type_, title, url)
    )
    db.commit()
    db.close()
