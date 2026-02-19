# School Management Web System (Flask + SQLite + HTML/JS)

A complete LAN-ready school dashboard with AI commands, charts, and manual/ESP32-style ingestion.

## Features
- Flask backend + SQLite DB with these tables:
  - Attendance(name, date, teacher)
  - Performance(name, subject, marks, date, teacher)
  - Discipline(name, case_desc, date, teacher, severity)
  - Event(event_name, date, description, teacher)
- REST endpoints:
  - `GET /display/<category>`
  - `POST /add/<category>`
  - `POST /ask`
- AI processing with OpenAI GPT (actionable JSON auto-insert support)
- Server-side TTS via gTTS (+ browser fallback voice customization)
- Bootstrap + Chart.js frontend:
  - list records, search/filter, latest entry,
  - attendance/performance charts,
  - AI chat panel,
  - manual add to simulate ESP32 posts,
  - localStorage offline cache,
  - optional browser event notifications.

## Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export OPENAI_API_KEY="your_api_key"   # optional for /ask AI
python app.py
```

Then open:
- Local: `http://127.0.0.1:5000`
- LAN: `http://<your-local-ip>:5000`

To find your LAN IP:
```bash
hostname -I
```

## API examples
### Add attendance
```bash
curl -X POST http://127.0.0.1:5000/add/attendance \
  -H "Content-Type: application/json" \
  -d '{"name":"Aisha","date":"2026-02-19","teacher":"Mr. Khan"}'
```

### Ask AI
```bash
curl -X POST http://127.0.0.1:5000/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"Mark attendance for Aisha"}'
```

## ESP32 WiFi POST integration notes
Use `HTTPClient` on ESP32 to POST JSON data to the Flask host IP.

```cpp
#include <WiFi.h>
#include <HTTPClient.h>

const char* ssid = "YOUR_WIFI";
const char* password = "YOUR_PASS";
const char* serverUrl = "http://192.168.1.10:5000/add/attendance"; // Flask PC IP

void setup() {
  Serial.begin(115200);
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) { delay(500); }

  HTTPClient http;
  http.begin(serverUrl);
  http.addHeader("Content-Type", "application/json");

  String payload = "{\"name\":\"Aisha\",\"date\":\"2026-02-19\",\"teacher\":\"ESP32-Node\"}";
  int code = http.POST(payload);
  String response = http.getString();
  Serial.println(code);
  Serial.println(response);
  http.end();
}

void loop() {}
```

## AI commands supported
- `Mark attendance for [name]`
- `Add performance for [name] in [subject] [marks]`
- `Organize event [event_name] [date]`
- `Show attendance`
- `Show performance summary for [name]`

The `/ask` endpoint expects model-generated JSON and can auto-insert data records when action=`insert`.
