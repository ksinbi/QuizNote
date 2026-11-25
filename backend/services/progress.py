"""문제 생성 작업의 단계별 진행 상황 (로딩 화면 표시용, 메모리 보관)."""
import threading
import time
import uuid

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


def start(session_id: str) -> str | None:
    """작업 시작 → 작업 ID. 이미 진행 중이면 None."""
    with _lock:
        _cleanup()
        if _jobs.get(session_id, {}).get("status") == "running":
            return None
        job_id = uuid.uuid4().hex
        _jobs[session_id] = {
            "job_id": job_id, "status": "running", "stage": STAGES[0][0], "detail": "", "error": "", "updated": time.time()
        }
        return job_id


def cancel(session_id: str) -> bool:
    """진행 중인 작업을 취소 표시. 작업 스레드는 끝까지 돌지만 결과는 저장되지 않습니다."""
    with _lock:
        job = _jobs.get(session_id)
        if not job or job["status"] != "running":
            return False
        job.update(status="cancelled", detail="", updated=time.time())
        return True


def is_current(session_id: str, job_id: str) -> bool:
    """이 작업이 아직 유효한(취소되거나 새 작업으로 바뀌지 않은) 작업인지."""
    with _lock:
        job = _jobs.get(session_id)
        return bool(job and job.get("job_id") == job_id and job["status"] == "running")


def set_stage(session_id: str, stage: str, detail: str = "") -> None:
    with _lock:
        job = _jobs.get(session_id)
        if job and job["status"] == "running":
            job.update(stage=stage, detail=detail, updated=time.time())


def finish(session_id: str, job_id: str) -> None:
    with _lock:
        job = _jobs.get(session_id)
        if job and job.get("job_id") == job_id and job["status"] == "running":
            job.update(status="done", stage=STAGES[-1][0], detail="", updated=time.time())


def fail(session_id: str, message: str, job_id: str) -> None:
    with _lock:
        job = _jobs.get(session_id)
        if job and job.get("job_id") == job_id and job["status"] == "running":
            job.update(status="error", error=message, updated=time.time())


def get(session_id: str) -> dict:
    with _lock:
        job = dict(_jobs.get(session_id) or {"status": "idle", "stage": "", "detail": "", "error": ""})
    job.pop("updated", None)
    job.pop("job_id", None)
    job["stage_index"] = _STAGE_INDEX.get(job["stage"], -1)
    job["stages"] = [{"key": k, "label": label} for k, label in STAGES]
    return job
