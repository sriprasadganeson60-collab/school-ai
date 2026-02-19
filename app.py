import base64
import io
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template, request
from flask_cors import CORS

try:
    from gtts import gTTS
except ImportError:  # pragma: no cover - optional runtime dependency handling
    gTTS = None

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "school.db"

app = Flask(__name__)
CORS(app)


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS Attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                date TEXT NOT NULL,
                teacher TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS Performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                subject TEXT NOT NULL,
                marks REAL NOT NULL,
                date TEXT NOT NULL,
                teacher TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS Discipline (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                case_desc TEXT NOT NULL,
                date TEXT NOT NULL,
                teacher TEXT NOT NULL,
                severity TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS Event (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_name TEXT NOT NULL,
                date TEXT NOT NULL,
                description TEXT NOT NULL,
                teacher TEXT NOT NULL
            );
            """
        )


CATEGORY_CONFIG = {
    "attendance": {
        "table": "Attendance",
        "fields": ["name", "date", "teacher"],
    },
    "performance": {
        "table": "Performance",
        "fields": ["name", "subject", "marks", "date", "teacher"],
    },
    "discipline": {
        "table": "Discipline",
        "fields": ["name", "case_desc", "date", "teacher", "severity"],
    },
    "event": {
        "table": "Event",
        "fields": ["event_name", "date", "description", "teacher"],
    },
}


def normalize_payload(payload: dict, category: str) -> dict:
    data = payload.copy()
    if "date" not in data or not data["date"]:
        data["date"] = datetime.now().strftime("%Y-%m-%d")

    if category == "performance" and "marks" in data:
        data["marks"] = float(data["marks"])

    return data


def insert_record(category: str, payload: dict) -> dict:
    config = CATEGORY_CONFIG[category]
    data = normalize_payload(payload, category)

    missing = [field for field in config["fields"] if field not in data]
    if missing:
        raise ValueError(f"Missing required fields: {', '.join(missing)}")

    columns = ", ".join(config["fields"])
    placeholders = ", ".join(["?"] * len(config["fields"]))
    values = [data[field] for field in config["fields"]]

    with get_conn() as conn:
        cursor = conn.execute(
            f"INSERT INTO {config['table']} ({columns}) VALUES ({placeholders})", values
        )
        record_id = cursor.lastrowid
        row = conn.execute(
            f"SELECT * FROM {config['table']} WHERE id = ?", (record_id,)
        ).fetchone()

    return dict(row)


def fetch_records(category: str):
    table = CATEGORY_CONFIG[category]["table"]
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM {table} ORDER BY date DESC, id DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def tts_to_base64(text: str) -> str | None:
    if not text or gTTS is None:
        return None

    try:
        fp = io.BytesIO()
        gTTS(text=text, lang="en").write_to_fp(fp)
        fp.seek(0)
        return base64.b64encode(fp.read()).decode("utf-8")
    except Exception:
        return None


def build_prompt(question: str) -> str:
    return (
        "You are a school management AI assistant. "
        "If the user asks for an insertion command, return JSON only in this exact schema: "
        '{"action":"insert","category":"attendance|performance|discipline|event","data":{...},"message":"human readable"}. '
        "For query/report requests, return JSON with schema: "
        '{"action":"query","target":"attendance|performance|discipline|event|summary","name":"optional","message":"human readable"}. '
        "If it's only conversational, return JSON: "
        '{"action":"chat","message":"..."}. '
        f"User input: {question}"
    )


def call_openai(question: str) -> dict:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or OpenAI is None:
        return {"action": "chat", "message": "OpenAI API key not configured. Use manual forms or set OPENAI_API_KEY."}

    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        messages=[
            {"role": "system", "content": "Respond only with valid JSON."},
            {"role": "user", "content": build_prompt(question)},
        ],
        temperature=0.2,
    )
    content = response.choices[0].message.content or "{}"
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {"action": "chat", "message": content}


init_db()

@app.route("/")
def index():
    return render_template("index.html")


@app.get("/display/<category>")
def display_category(category: str):
    category = category.lower()
    if category not in CATEGORY_CONFIG:
        return jsonify({"error": "Invalid category"}), 400
    return jsonify(fetch_records(category))


@app.post("/add/<category>")
def add_category(category: str):
    category = category.lower()
    if category not in CATEGORY_CONFIG:
        return jsonify({"error": "Invalid category"}), 400

    payload = request.get_json(silent=True) or {}
    try:
        record = insert_record(category, payload)
        return jsonify({"status": "ok", "record": record})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:  # pragma: no cover
        return jsonify({"error": f"Failed to add record: {exc}"}), 500


@app.post("/ask")
def ask_ai():
    body = request.get_json(silent=True) or {}
    question = body.get("question", "").strip()
    if not question:
        return jsonify({"error": "Question is required"}), 400

    ai_json = call_openai(question)
    inserted_record = None

    if ai_json.get("action") == "insert":
        category = (ai_json.get("category") or "").lower()
        data = ai_json.get("data") or {}
        if category in CATEGORY_CONFIG:
            try:
                inserted_record = insert_record(category, data)
                ai_json["message"] = ai_json.get("message") or f"Inserted {category} record successfully."
            except Exception as exc:
                ai_json["message"] = f"AI suggested insert but failed: {exc}"

    if ai_json.get("action") == "query":
        target = (ai_json.get("target") or "").lower()
        name = (ai_json.get("name") or "").strip()
        if target in CATEGORY_CONFIG:
            ai_json["results"] = fetch_records(target)
        elif target == "summary" and name:
            perf = fetch_records("performance")
            student = [r for r in perf if r["name"].lower() == name.lower()]
            avg = round(sum(r["marks"] for r in student) / len(student), 2) if student else 0
            ai_json["results"] = {
                "name": name,
                "records": student,
                "average_marks": avg,
            }

    message = ai_json.get("message", "Done")
    audio_b64 = tts_to_base64(message)

    return jsonify(
        {
            "response": ai_json,
            "inserted_record": inserted_record,
            "tts_audio_base64": audio_b64,
            "tts_mime": "audio/mpeg" if audio_b64 else None,
        }
    )


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
