from flask import Blueprint, request, jsonify, session
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_db

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/api/register", methods=["POST"])
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
            (username, email, generate_password_hash(password))
        )
        db.commit()
        user = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        db.close()
        return jsonify({"success": True, "username": username})
    except sqlite3.IntegrityError:
        return jsonify({"error": "Username or email already exists"}), 400

@auth_bp.route("/api/login", methods=["POST"])
def login():
    data = request.json
    username = data.get("username", "").strip()
    password = data.get("password", "")
    db = get_db()
    user = db.execute(
        "SELECT * FROM users WHERE username=? OR email=?",
        (username, username)
    ).fetchone()
    db.close()
    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Invalid credentials"}), 401
    session["user_id"] = user["id"]
    session["username"] = user["username"]
    return jsonify({"success": True, "username": user["username"]})

@auth_bp.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"success": True})

@auth_bp.route("/api/me")
def me():
    if "user_id" not in session:
        return jsonify({"authenticated": False})
    return jsonify({"authenticated": True, "username": session["username"], "user_id": session["user_id"]})
