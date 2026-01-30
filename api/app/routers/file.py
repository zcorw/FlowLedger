from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import resolve_user_id
from ..db import SessionLocal
from ..import_tasks import save_upload_file
from ..models import FileAsset, User

router = APIRouter(prefix="/v1/files", tags=["file"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def get_current_user(
    db: Session = Depends(get_db),
    user_id: int = Depends(resolve_user_id),
) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="user_not_found")
    return user


class FileMetaOut(BaseModel):
    id: int
    filename: str
    content_type: Optional[str] = None
    size: int
    created_at: datetime


@router.post("", status_code=201, response_model=FileMetaOut)
def upload_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stored_path = save_upload_file(file)
    now = _now()
    meta = FileAsset(
        user_id=current_user.id,
        filename=file.filename or "",
        content_type=file.content_type,
        storage_path=str(stored_path),
        size=stored_path.stat().st_size,
        created_at=now,
        updated_at=now,
    )
    db.add(meta)
    db.commit()
    db.refresh(meta)
    return FileMetaOut(
        id=meta.id,
        filename=meta.filename,
        content_type=meta.content_type,
        size=meta.size,
        created_at=meta.created_at,
    ).model_dump()


@router.get("/{file_id}", response_model=FileMetaOut)
def get_file_meta(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    meta = (
        db.query(FileAsset)
        .filter(FileAsset.id == file_id, FileAsset.user_id == current_user.id)
        .first()
    )
    if not meta:
        raise HTTPException(status_code=404, detail="file_not_found")
    return FileMetaOut(
        id=meta.id,
        filename=meta.filename,
        content_type=meta.content_type,
        size=meta.size,
        created_at=meta.created_at,
    ).model_dump()
