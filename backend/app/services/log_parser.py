import re
from collections import Counter, defaultdict, deque
from pathlib import Path

from .privacy_filter import mask

THREADTIME = re.compile(r"^(?P<time>\d\d-\d\d\s+\d\d:\d\d:\d\d\.\d+)\s+\d+\s+\d+\s+(?P<level>[VDIWEF])\s+(?P<tag>[^:]+):\s*(?P<message>.*)$")
SIGNALS = {
    "connection": ("연결·전송", re.compile(r"^(CAR\.GAL\.GAL\.LITE|CAR\.XFER\.LITE|GH\.CarClientManager|GH\.GHLifetimeManager)$", re.I), re.compile(r"head.?unit|android auto|car token disconnect", re.I)),
    "audio": ("오디오 포커스", re.compile(r"^(AudioFocus|CAR\.AUDIO\.(FOCUS|AFM)|YTPL\.audiomanager|PlaybackAudioManager)$", re.I), re.compile(r"audio.?focus|STOPPAGE_REASON_AUDIO_FOCUS", re.I)),
    "display": ("화면·비디오", re.compile(r"^(ModeChangeObserver|LogicalDisplayMapper)$", re.I), re.compile(r"video.?focus|virtual display snapshot|display removed", re.I)),
}


def iter_events(path: str | None, serial: str | None = None):
    if not path or not Path(path).is_file():
        return
    with Path(path).open("r", encoding="utf-8", errors="replace") as stream:
        for line_no, raw in enumerate(stream, 1):
            matched = THREADTIME.match(raw.rstrip("\r\n"))
            if matched:
                yield {"id": f"L{line_no}", "line": line_no, "time": matched["time"], "level": matched["level"], "tag": mask(matched["tag"].strip(), serial), "message": mask(matched["message"], serial)}


def signal_for(entry: dict) -> str | None:
    return next((key for key, (_, tag_pattern, message_pattern) in SIGNALS.items() if tag_pattern.search(entry["tag"]) or message_pattern.search(entry["message"])), None)


def parse(path: str | None, serial: str | None = None, level: str | None = None, query: str | None = None, limit: int = 500):
    if not path or not Path(path).is_file():
        return []
    result = []
    seen = set()
    for entry in iter_events(path, serial):
        if level and entry["level"] not in level:
            continue
        if query and query.lower() not in (entry["tag"] + " " + entry["message"]).lower():
            continue
        signature = (entry["level"], entry["tag"], entry["message"])
        if signature in seen:
            continue
        seen.add(signature)
        result.append(entry)
        if len(result) >= limit:
            break
    return result


def profile(path: str | None, serial: str | None = None):
    levels = Counter()
    minutes = defaultdict(Counter)
    tags = Counter()
    signals = {key: {"label": label, "count": 0, "examples": []} for key, (label, _, _) in SIGNALS.items()}
    total = 0
    for entry in iter_events(path, serial):
        total += 1
        levels[entry["level"]] += 1
        minutes[entry["time"][:11]][entry["level"]] += 1
        if entry["level"] in "WEF":
            tags[entry["tag"]] += 1
        category = signal_for(entry)
        if category:
            group = signals[category]
            group["count"] += 1
            if len(group["examples"]) < 5 and entry["level"] in "WEF":
                group["examples"].append(entry)
    return {
        "total": total,
        "levels": {key: levels[key] for key in "VDIWEF"},
        "timeline": [{"minute": minute, "total": sum(counts.values()), "warnings": counts["W"], "errors": counts["E"] + counts["F"]} for minute, counts in sorted(minutes.items())],
        "top_tags": [{"tag": tag, "count": count} for tag, count in tags.most_common(8)],
        "signals": signals,
        "note": "Logcat 빈도와 키워드 분류입니다. 경고·오류 수는 테스트 실패나 원인을 의미하지 않습니다.",
    }


def diagnostic_events(path: str | None, serial: str | None = None, limit: int = 60, case_id: str | None = None):
    buckets = {key: deque(maxlen=limit) for key in SIGNALS}
    fallback = deque(maxlen=10)
    for entry in iter_events(path, serial):
        category = signal_for(entry)
        if category:
            buckets[category].append(entry)
        elif entry["level"] in "EF":
            fallback.append(entry)
    focus = "audio" if case_id == "TC-03" else "display" if case_id in {"TC-02", "TC-04", "TC-05"} else "connection"
    selected = list(buckets[focus])[-(limit - 12):]
    for key, bucket in buckets.items():
        if key != focus:
            selected.extend(list(bucket)[-6:])
    return sorted((selected or list(fallback))[-limit:], key=lambda entry: entry["line"])
