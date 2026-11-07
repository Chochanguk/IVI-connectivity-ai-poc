import os
import subprocess
from pathlib import Path


def adb_path() -> Path:
    custom = os.getenv("ADB_PATH", "").strip()
    if custom:
        return Path(custom)
    local = os.getenv("LOCALAPPDATA", "")
    if local:
        return Path(local) / "Android" / "Sdk" / "platform-tools" / "adb.exe"
    return Path("adb")


def run_adb(*args: str, timeout: int = 8) -> subprocess.CompletedProcess[str]:
    path = adb_path()
    if path != Path("adb") and not path.is_file():
        raise RuntimeError(f"ADB 실행 파일을 찾을 수 없습니다: {path}")
    try:
        return subprocess.run([str(path), *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"ADB 실행 실패: {type(exc).__name__}") from exc


def devices() -> tuple[str, list[str]]:
    result = run_adb("devices")
    if result.returncode:
        raise RuntimeError("ADB 장치 목록 조회 실패")
    rows = [line.split("\t", 1) for line in result.stdout.splitlines()[1:] if "\t" in line]
    ready = [serial for serial, state in rows if state.strip() == "device"]
    if len(ready) > 1:
        return "multiple", ready
    if ready:
        return "connected", ready
    if any(state.strip() == "unauthorized" for _, state in rows):
        return "unauthorized", []
    return "disconnected", []


def status() -> dict:
    path = adb_path()
    try:
        state, ready = devices()
        data = {"state": state, "adb_path": str(path), "adb_ready": True, "model": None, "android_version": None, "message": None}
        if state == "connected":
            serial = ready[0]
            for key, prop in (("model", "ro.product.model"), ("android_version", "ro.build.version.release")):
                result = run_adb("-s", serial, "shell", "getprop", prop)
                if result.returncode == 0:
                    data[key] = result.stdout.strip() or None
        elif state == "unauthorized":
            data["message"] = "스마트폰에서 USB 디버깅을 허용하세요."
        elif state == "multiple":
            data["message"] = "ADB 장치가 여러 대입니다. 한 대만 연결하세요."
        else:
            data["message"] = "ADB 장치가 연결되지 않았습니다."
        return data
    except RuntimeError as exc:
        return {"state": "error", "adb_path": str(path), "adb_ready": False, "model": None, "android_version": None, "message": str(exc)}


def single_serial() -> str:
    state, ready = devices()
    if state != "connected":
        raise RuntimeError(f"수집 가능한 단일 장치가 없습니다: {state}")
    return ready[0]
