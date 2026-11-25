"""문제 생성 작업의 단계별 진행 상황 (로딩 화면 표시용, 메모리 보관)."""
import threading
import time

STAGES: list[tuple[str, str]] = [
    ("extract", "문서 내용 추출"),
    ("analyze", "핵심 내용 분석"),
    ("generate", "조건에 맞춰 문제 생성"),
    ("answers", "정답 및 해설 검증"),
    ("sources", "원문 출처 연결"),
]
_STAGE_INDEX = {key: i for i, (key, _) in enumerate(STAGES)}
_TTL = 60 * 60

_jobs: dict[str, dict] = {}
_lock = threading.Lock()


def _cleanup() -> None:
    now = time.time()
    for sid in [s for s, j in _jobs.items() if j["status"] != "running" and now - j["updated"] > _TTL]:
        _jobs.pop(sid, None)


def start(session_id: str) -> bool:
    """작업 시작. 이미 진행 중이면 False."""
    with _lock:
        _cleanup()
        if _jobs.get(session_id, {}).get("status") == "running":
            return False
        _jobs[session_id] = {"status": "running", "stage": STAGES[0][0], "detail": "", "error": "", "updated": time.time()}
        return True


def set_stage(session_id: str, stage: str, detail: str = "") -> None:
    with _lock:
        job = _jobs.get(session_id)
        if job and job["status"] == "running":
            job.update(stage=stage, detail=detail, updated=time.time())


def finish(session_id: str) -> None:
    with _lock:
        if session_id in _jobs:
            _jobs[session_id].update(status="done", stage=STAGES[-1][0], detail="", updated=time.time())


def fail(session_id: str, message: str) -> None:
    with _lock:
        if session_id in _jobs:
            _jobs[session_id].update(status="error", error=message, updated=time.time())


def get(session_id: str) -> dict:
    with _lock:
        job = dict(_jobs.get(session_id) or {"status": "idle", "stage": "", "detail": "", "error": ""})
    job.pop("updated", None)
    job["stage_index"] = _STAGE_INDEX.get(job["stage"], -1)
    job["stages"] = [{"key": k, "label": label} for k, label in STAGES]
    return job
