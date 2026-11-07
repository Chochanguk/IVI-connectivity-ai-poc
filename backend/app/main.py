import json
from pathlib import Path
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from app.ai.diagnostics import analyze
from app.services import adb_service, log_collector, log_parser, store
from app.services.privacy_filter import mask

app = FastAPI(title="IVI Connectivity AI PoC")
app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"], allow_methods=["GET", "POST", "PATCH"], allow_headers=["*"])


class NewSession(BaseModel):
    case_id: str


class ResultInput(BaseModel):
    status: str
    actual_result: str = Field(default="", max_length=2000)
    notes: str = Field(default="", max_length=2000)
    screenshot: str = Field(default="", max_length=260)


class AnalysisInput(BaseModel):
    use_ai: bool = False


def public(session: dict):
    result = dict(session)
    serial = result.pop("device_serial", None)
    result["actual_result"] = mask(result["actual_result"], serial)
    result["notes"] = mask(result["notes"], serial)
    result["screenshot"] = mask(result["screenshot"], serial)
    result["log_file"] = Path(result["log_file"]).name if result["log_file"] else None
    if result["analysis_json"]:
        result["analysis"] = json.loads(result.pop("analysis_json"))
    else:
        result.pop("analysis_json")
        result["analysis"] = None
    return result


def require_session(session_id: str):
    session = log_collector.reconcile(session_id)
    if not session:
        raise HTTPException(404, "세션을 찾을 수 없습니다.")
    return session


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/device")
def device():
    return adb_service.status()


@app.get("/api/cases")
def cases():
    return [{"id": c[0], "name": c[1], "purpose": c[2], "steps": c[3], "expected": c[4]} for c in store.CASES]


@app.get("/api/sessions")
def sessions():
    return [public(log_collector.reconcile(s["id"])) for s in store.list_sessions()]


@app.post("/api/sessions")
def create_session(body: NewSession):
    try:
        return public(store.create(body.case_id))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.patch("/api/sessions/{session_id}")
def record_result(session_id: str, body: ResultInput):
    session = require_session(session_id)
    if body.status not in {"PASS", "FAIL", "NOT_RUN", "BLOCKED"}:
        raise HTTPException(400, "잘못된 판정")
    if body.status in {"PASS", "FAIL"} and not body.actual_result.strip():
        raise HTTPException(400, "PASS/FAIL 판정에는 실제 결과가 필요합니다.")
    if body.status != "NOT_RUN" and session["collection_state"] == "collecting":
        raise HTTPException(409, "수집을 먼저 중지하세요.")
    return public(store.update(session_id, status=body.status, actual_result=body.actual_result, notes=body.notes, screenshot=body.screenshot, ended_at=store.now() if body.status != "NOT_RUN" else session["ended_at"]))


@app.post("/api/sessions/{session_id}/logs/start")
def start_logs(session_id: str):
    require_session(session_id)
    try:
        return public(log_collector.start(session_id))
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/api/sessions/{session_id}/logs/stop")
def stop_logs(session_id: str):
    require_session(session_id)
    return public(log_collector.stop(session_id))


@app.get("/api/sessions/{session_id}/logs")
def logs(session_id: str, level: str | None = Query(default=None, pattern="^[VDIWEF]+$"), q: str | None = Query(default=None, max_length=100)):
    session = require_session(session_id)
    return log_parser.parse(session["log_file"], serial=session["device_serial"], level=level, query=q)


@app.get("/api/sessions/{session_id}/log-stats")
def log_stats(session_id: str):
    session = require_session(session_id)
    return log_parser.profile(session["log_file"], session["device_serial"])


@app.get("/api/sessions/{session_id}/logs/download", response_class=PlainTextResponse)
def download_logs(session_id: str):
    session = require_session(session_id)
    events = log_parser.parse(session["log_file"], serial=session["device_serial"], limit=10000)
    return "\n".join(f"{e['id']} {e['time']} {e['level']} {e['tag']}: {e['message']}" for e in events)


@app.post("/api/sessions/{session_id}/analyze")
def analyze_session(session_id: str, body: AnalysisInput):
    session = require_session(session_id)
    case = next(c for c in store.CASES if c[0] == session["case_id"])
    events = log_parser.diagnostic_events(session["log_file"], serial=session["device_serial"], case_id=session["case_id"])
    stats = log_parser.profile(session["log_file"], session["device_serial"])
    try:
        result, source = analyze(session, case, events, body.use_ai, stats)
    except Exception as exc:
        raise HTTPException(502, f"진단 실패: {type(exc).__name__}") from exc
    wrapped = {"source": source, "model": __import__("os").getenv("OPENAI_MODEL", "gpt-6-luna") if source == "openai" else None, "result": result.model_dump(), "created_at": store.now()}
    store.update(session_id, analysis_json=json.dumps(wrapped, ensure_ascii=False))
    return wrapped


@app.get("/api/report", response_class=PlainTextResponse)
def report():
    sessions = store.list_sessions()
    counts = {status: sum(s["status"] == status for s in sessions) for status in ("PASS", "FAIL", "BLOCKED", "NOT_RUN")}
    lines = ["# IVI 폰 연결 검증 보고서", "", "실제 수행 세션 기록. 미실행 세션은 검증 결과로 계산하지 않습니다.", "", f"통과 {counts['PASS']} / 실패 {counts['FAIL']} / 진행 불가 {counts['BLOCKED']} / 미실행 {counts['NOT_RUN']}", ""]
    for session in sessions:
        case = next(c for c in store.CASES if c[0] == session["case_id"])
        label = {"PASS": "통과", "FAIL": "실패", "BLOCKED": "진행 불가", "NOT_RUN": "미실행"}[session["status"]]
        local_time = datetime.fromisoformat(session["started_at"]).astimezone(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M:%S KST")
        lines += [f"## {case[0]} {case[1]} — {label}", "", f"- 실행: {local_time}", f"- 기대 결과: {case[4]}", f"- 실제 결과: {mask(session['actual_result'], session['device_serial']) or '미기록'}", f"- 메모: {mask(session['notes'], session['device_serial']) or '없음'}", f"- 로그: {Path(session['log_file']).name if session['log_file'] else '없음'}", ""]
        if session["analysis_json"]:
            analysis = json.loads(session["analysis_json"])
            source_label = "OpenAI" if analysis["source"] == "openai" else "규칙 기반"
            lines += [f"- 진단 출처: {source_label}", f"- 진단 요약: {analysis['result']['summary']}", ""]
    return "\n".join(lines)
