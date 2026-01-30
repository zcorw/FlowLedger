from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class ImportTaskCreateResponse(BaseModel):
    task_id: str
    file_id: Optional[int] = None


class ImportTaskStatus(BaseModel):
    task_id: str
    kind: str
    status: str
    progress: int
    stage: Optional[str] = None
    filename: Optional[str] = None
    size: Optional[int] = None
    result: Optional[Any] = None
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime
