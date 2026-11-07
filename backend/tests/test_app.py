import os
from pathlib import Path

os.environ["RESULTS_DIR"] = str(Path(__file__).parent / ".test-results")

from fastapi.testclient import TestClient
from app.main import app
from app.services import adb_service, log_parser, store
from app.ai.diagnostics import Analysis, Hypothesis, validate_evidence

client = TestClient(app)


def test_device_status_mock(monkeypatch):
    monkeypatch.setattr(adb_service, "status", lambda: {"state": "connected", "adb_ready": True, "model": "Galaxy", "android_version": "15", "adb_path": "adb", "message": None})
    response = client.get("/api/device")
    assert response.status_code == 200
    assert response.json()["model"] == "Galaxy"


def test_session_and_evidence(tmp_path):
    session = client.post("/api/sessions", json={"case_id": "TC-01"}).json()
    assert session["status"] == "NOT_RUN"
    assert client.patch(f"/api/sessions/{session['id']}", json={"status": "PASS"}).status_code == 400
    saved = client.patch(f"/api/sessions/{session['id']}", json={"status": "FAIL", "actual_result": "화면이 나오지 않음"}).json()
    assert saved["status"] == "FAIL"
    result = client.post(f"/api/sessions/{session['id']}/analyze", json={"use_ai": False}).json()
    assert result["source"] == "rules"
    assert result["result"]["hypotheses"] == []
    log = tmp_path / "sample.log"
    log.write_text("11-07 12:00:00.000  123  123 E Conn: serial=ABC123 email a@example.com\n", encoding="utf-8")
    events = log_parser.parse(str(log), serial="ABC123")
    assert events[0]["id"] == "L1"
    assert "ABC123" not in events[0]["message"]
    assert "a@example.com" not in events[0]["message"]
    invalid = Analysis(summary="x", observations=[], evidence_ids=["L2"], hypotheses=[Hypothesis(cause="x", evidence_ids=[], status="unverified", next_step="check")], next_steps=[], limitations=[])
    try:
        validate_evidence(invalid, events)
        assert False, "invalid evidence accepted"
    except ValueError:
        pass


def test_log_endpoints_never_expose_serial(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "RESULTS", tmp_path)
    session = client.post("/api/sessions", json={"case_id": "TC-02"}).json()
    log = tmp_path / "raw.log"
    log.write_text("11-07 12:00:00.000  123  123 W Tag: device ABC123\n", encoding="utf-8")
    store.update(session["id"], log_file=str(log), device_serial="ABC123", actual_result="ABC123 disconnected")
    listed = client.get("/api/sessions").json()
    assert "ABC123" not in str(listed)
    downloaded = client.get(f"/api/sessions/{session['id']}/logs/download").text
    assert "ABC123" not in downloaded
    assert "[DEVICE_ID]" in downloaded


def test_log_stats_and_late_diagnostic_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "RESULTS", tmp_path)
    session = client.post("/api/sessions", json={"case_id": "TC-03"}).json()
    log = tmp_path / "focus.log"
    noise = "".join(f"11-07 12:00:{i%60:02d}.000  123  123 W ContentProvider: Transport query unrelated warning {i}\n" for i in range(1200))
    log.write_text(noise + "11-07 12:01:00.000  123  123 W AudioFocus: LOSS device ABC123\n" + "11-07 12:01:05.000  123  123 I AudioFocus: GAIN device ABC123\n", encoding="utf-8")
    store.update(session["id"], log_file=str(log), device_serial="ABC123")
    response = client.get(f"/api/sessions/{session['id']}/log-stats")
    assert response.status_code == 200
    stats = response.json()
    assert stats["total"] == 1202
    assert stats["levels"]["W"] == 1201
    assert stats["signals"]["audio"]["count"] == 2
    assert stats["signals"]["connection"]["count"] == 0
    assert stats["signals"]["audio"]["examples"][0]["id"] == "L1201"
    assert "ABC123" not in response.text
    evidence = log_parser.diagnostic_events(str(log), serial="ABC123")
    assert [e["id"] for e in evidence] == ["L1201", "L1202"]
