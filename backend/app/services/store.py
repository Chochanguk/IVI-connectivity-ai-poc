import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RESULTS = Path(os.getenv("RESULTS_DIR", str(ROOT / "results")))

CASES = [
    ("TC-01", "연결 확인", "DHU 연결 및 화면 출력 확인", "ADB 포워딩과 DHU 실행 후 스마트폰 연결·화면을 관찰", "Android Auto 화면 표시"),
    ("TC-02", "화면 모드 전환", "주간/야간 전환 확인", "DHU에서 지원되는 주간/야간 모드 전환 후 화면 관찰", "모드에 맞게 화면 변경"),
    ("TC-03", "오디오 포커스", "오디오 포커스 해제·복구", "DHU에서 오디오 포커스 변경 후 재생 상태 관찰", "포커스 복구 후 정상 재생"),
    ("TC-04", "비디오 포커스", "비디오 포커스 해제·복귀", "DHU에서 비디오 포커스 변경 후 화면 관찰", "화면 복귀"),
    ("TC-05", "주행 제한", "주행 제한 UI 관찰", "DHU의 주행 상태 시뮬레이션 후 UI 관찰", "제한 대상 UI 동작 변경"),
    ("TC-06", "재연결", "USB 재연결 복구 확인", "수집 중지 후 사용자가 USB 분리·재연결, 새 세션에서 관찰", "다시 연결 및 화면 복구"),
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect():
    RESULTS.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(RESULTS / "sessions.sqlite3")
    db.row_factory = sqlite3.Row
    db.execute("""CREATE TABLE IF NOT EXISTS sessions (
        id TEXT PRIMARY KEY, case_id TEXT NOT NULL, started_at TEXT NOT NULL,
        ended_at TEXT, status TEXT NOT NULL DEFAULT 'NOT_RUN', actual_result TEXT NOT NULL DEFAULT '',
        notes TEXT NOT NULL DEFAULT '', screenshot TEXT NOT NULL DEFAULT '',
        log_file TEXT, device_serial TEXT, collection_state TEXT NOT NULL DEFAULT 'idle', analysis_json TEXT)""")
    db.commit()
    return db


def row(session_id: str):
    with connect() as db:
        found = db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
    return dict(found) if found else None


def list_sessions():
    with connect() as db:
        return [dict(r) for r in db.execute("SELECT * FROM sessions ORDER BY started_at DESC")]


def create(case_id: str):
    if case_id not in {case[0] for case in CASES}:
        raise ValueError("알 수 없는 테스트 ID")
    session_id = str(uuid.uuid4())
    with connect() as db:
        db.execute("INSERT INTO sessions(id,case_id,started_at) VALUES(?,?,?)", (session_id, case_id, now()))
        db.commit()
    return row(session_id)


def update(session_id: str, **fields):
    allowed = {"ended_at", "status", "actual_result", "notes", "screenshot", "log_file", "device_serial", "collection_state", "analysis_json"}
    if not row(session_id):
        raise KeyError(session_id)
    if not fields or not set(fields).issubset(allowed):
        raise ValueError("허용되지 않은 필드")
    columns = ", ".join(f"{key}=?" for key in fields)
    with connect() as db:
        db.execute(f"UPDATE sessions SET {columns} WHERE id=?", (*fields.values(), session_id))
        db.commit()
    return row(session_id)
