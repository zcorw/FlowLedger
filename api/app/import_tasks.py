from __future__ import annotations

import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Optional

from fastapi import HTTPException, UploadFile


_TASKS: Dict[str, Dict[str, Any]] = {}
_LOCK = Lock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def get_upload_dir() -> Path:
    root = os.getenv("UPLOAD_DIR", "./tmp/uploads")
    path = Path(root)
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_upload_file(upload: UploadFile) -> Path:
    filename = upload.filename or ""
    if not filename:
        raise HTTPException(status_code=422, detail="missing_filename")

    suffix = Path(filename).suffix
    dest = get_upload_dir() / f"{uuid.uuid4().hex}{suffix}"
    with dest.open("wb") as out:
        shutil.copyfileobj(upload.file, out)
    upload.file.close()
    return dest


def create_task(kind: str, filename: str, size: int, owner_id: Optional[int] = None) -> str:
    task_id = str(uuid.uuid4())
    now = _now()
    task = {
        "task_id": task_id,
        "kind": kind,
        "status": "queued",
        "progress": 0,
        "stage": "queued",
        "filename": filename,
        "size": size,
        "owner_id": owner_id,
        "result": None,
        "error": None,
        "created_at": now,
        "updated_at": now,
    }
    with _LOCK:
        _TASKS[task_id] = task
    return task_id


def get_task(task_id: str) -> Optional[Dict[str, Any]]:
    with _LOCK:
        task = _TASKS.get(task_id)
        return dict(task) if task else None


def update_task(task_id: str, **updates: Any) -> None:
    with _LOCK:
        task = _TASKS.get(task_id)
        if not task:
            return
        task.update(updates)
        task["updated_at"] = _now()

