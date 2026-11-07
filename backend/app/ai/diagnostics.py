import json
import os

from pydantic import BaseModel, ConfigDict, Field

from app.services.privacy_filter import mask


class Hypothesis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cause: str
    evidence_ids: list[str]
    status: str
    next_step: str


class Analysis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str
    observations: list[str]
    evidence_ids: list[str]
    hypotheses: list[Hypothesis]
    next_steps: list[str]
    limitations: list[str]


def rule_analysis(session: dict, events: list[dict]) -> Analysis:
    observed = []
    if session["actual_result"]:
        observed.append(f"사용자 기록: {mask(session['actual_result'], session.get('device_serial'))}")
    observed.append(f"사용자 판정: {session['status']}")
    warnings = [event for event in events if event["level"] in "WEF"][:8]
    ids = [event["id"] for event in warnings]
    if not warnings:
        return Analysis(summary="분석 가능한 오류/경고 근거가 부족합니다.", observations=observed, evidence_ids=[], hypotheses=[], next_steps=["DHU 화면과 테스트 시각을 기록하고 새 Logcat 세션을 수집하세요."], limitations=["현재 로그만으로 연결 내부 상태 또는 원인을 판단할 수 없습니다."])
    return Analysis(summary="수집 로그에 경고/오류가 있습니다. 장애 연관성은 미확인입니다.", observations=observed, evidence_ids=ids, hypotheses=[Hypothesis(cause="관련 이벤트 여부 확인 필요", evidence_ids=ids, status="unverified", next_step="테스트 수행 시각과 근거 로그의 시각을 대조하세요.")], next_steps=["동일 절차를 재현하고 정상 세션의 로그와 비교하세요."], limitations=["경고/오류 로그만으로 연결 실패 또는 원인을 확정할 수 없습니다."])


def validate_evidence(analysis: Analysis, events: list[dict]):
    valid = {event["id"] for event in events}
    used = set(analysis.evidence_ids)
    for hypothesis in analysis.hypotheses:
        used.update(hypothesis.evidence_ids)
    unknown = used - valid
    if unknown:
        raise ValueError(f"존재하지 않는 로그 ID 참조: {sorted(unknown)}")
    if any(not hypothesis.next_step for hypothesis in analysis.hypotheses):
        raise ValueError("원인 후보에 검증 절차가 없습니다.")


def analyze(session: dict, case: tuple, events: list[dict], use_ai: bool, stats: dict | None = None) -> tuple[Analysis, str]:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not use_ai or not key:
        result = rule_analysis(session, events)
        validate_evidence(result, events)
        return result, "rules"
    from openai import OpenAI

    selected = events[-50:]
    stats = stats or {}
    payload = {
        "case": {"id": case[0], "purpose": case[2], "expected": case[4]},
        "status": session["status"],
        "actual_result": mask(session["actual_result"], session.get("device_serial")),
        "log_statistics": {"total": stats.get("total", 0), "levels": stats.get("levels", {}), "signals": {key: item["count"] for key, item in stats.get("signals", {}).items()}},
        "events": selected,
    }
    client = OpenAI(api_key=key, timeout=20, max_retries=0)
    response = client.responses.parse(
        model=os.getenv("OPENAI_MODEL", "gpt-6-luna"),
        instructions="당신은 IVI 연결 테스트 진단 보조자입니다. 사용자 판정과 로그 통계는 관찰 자료이며 인과관계 증거가 아닙니다. 관찰 사실과 가설을 구분하고, 경고 수만으로 장애를 확정하지 마세요. 제공된 로그 ID만 인용하세요. 각 가설에 검증 절차를 포함하세요. 근거 부족을 명시하세요. 한국어로 간결하게 답하세요.",
        input=json.dumps(payload, ensure_ascii=False),
        text_format=Analysis,
        max_output_tokens=1200,
        reasoning={"effort": "low"},
        store=False,
    )
    if response.output_parsed is None:
        raise RuntimeError("AI가 구조화된 응답을 반환하지 않았습니다.")
    result = Analysis.model_validate(response.output_parsed)
    validate_evidence(result, selected)
    return result, "openai"
