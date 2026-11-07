"""Explicit live ADB read and a short local Logcat capture. Does not grade a test."""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
device = client.get("/api/device").json()
print(json.dumps({key: value for key, value in device.items() if key != "adb_path"}, ensure_ascii=False))
if device["state"] != "connected":
    raise SystemExit("단일 ADB 장치가 연결되지 않았습니다.")
session = client.post("/api/sessions", json={"case_id": "TC-01"}).json()
print(f"Session: {session['id']} (NOT_RUN)")
try:
    started = client.post(f"/api/sessions/{session['id']}/logs/start")
    if started.status_code != 200:
        raise RuntimeError(started.text)
    time.sleep(2)
finally:
    stopped = client.post(f"/api/sessions/{session['id']}/logs/stop")
    print(f"Collector: {stopped.json().get('collection_state')}")
events = client.get(f"/api/sessions/{session['id']}/logs?level=VDIWEF").json()
print(f"Parsed masked events: {len(events)}")
print("No test verdict was recorded.")
