import atexit
import subprocess
import threading
import time
from pathlib import Path

from . import adb_service, store

_lock = threading.Lock()
_active: dict[str, tuple[subprocess.Popen, object]] = {}


def _cleanup():
    with _lock:
        active = list(_active.values())
    for process, stream in active:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
        stream.close()


atexit.register(_cleanup)


def _watch(session_id: str, process: subprocess.Popen, stream, serial: str):
    while process.poll() is None:
        time.sleep(2)
        if process.poll() is not None:
            break
        try:
            state, ready = adb_service.devices()
            if state != "connected" or serial not in ready:
                process.terminate()
        except RuntimeError:
            process.terminate()
    process.wait()
    with _lock:
        current = _active.get(session_id)
        if current and current[0] is process:
            del _active[session_id]
            stream.close()
            if store.row(session_id):
                store.update(session_id, collection_state="stopped", ended_at=store.now())


def start(session_id: str):
    session = store.row(session_id)
    if not session:
        raise KeyError(session_id)
    if session["log_file"]:
        raise ValueError("이 세션은 이미 수집을 시작했습니다. 새 세션을 만드세요.")
    serial = adb_service.single_serial()
    log_dir = store.RESULTS / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{session_id}.log"
    with _lock:
        if _active:
            raise ValueError("다른 세션에서 Logcat 수집 중입니다.")
        stream = log_path.open("wb")
        try:
            process = subprocess.Popen([str(adb_service.adb_path()), "-s", serial, "logcat", "-v", "threadtime", "-T", "1"], stdout=stream, stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except OSError:
            stream.close()
            log_path.unlink(missing_ok=True)
            raise RuntimeError("Logcat 실행 실패")
        time.sleep(0.15)
        if process.poll() is not None:
            stream.close()
            raise RuntimeError("Logcat이 즉시 종료되었습니다. ADB 연결을 확인하세요.")
        _active[session_id] = (process, stream)
        store.update(session_id, log_file=str(log_path), device_serial=serial, collection_state="collecting")
    threading.Thread(target=_watch, args=(session_id, process, stream, serial), daemon=True).start()
    return store.row(session_id)


def stop(session_id: str):
    if not store.row(session_id):
        raise KeyError(session_id)
    with _lock:
        active = _active.get(session_id)
    if active:
        process = active[0]
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
    store.update(session_id, collection_state="stopped", ended_at=store.now())
    return store.row(session_id)


def reconcile(session_id: str):
    with _lock:
        active = _active.get(session_id)
    session = store.row(session_id)
    if session and session["collection_state"] == "collecting" and not active:
        return store.update(session_id, collection_state="interrupted", ended_at=store.now())
    return session
