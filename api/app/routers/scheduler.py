from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from ..auth import resolve_user_id
from ..db import SessionLocal
from ..models import SchedulerJob, SchedulerJobRun, SchedulerConfirmation

router = APIRouter(prefix="/v1", tags=["scheduler"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _period_key(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M")


def _require_job_run(job_run_id: int, user_id: int, db: Session) -> SchedulerJobRun:
    run = db.get(SchedulerJobRun, job_run_id)
    if not run:
        raise HTTPException(status_code=404, detail="job_run_not_found")
    job = db.get(SchedulerJob, run.job_id)
    if not job or job.user_id != user_id:
        raise HTTPException(status_code=404, detail="job_run_not_found")
    return run


class JobCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: Optional[str] = Field(default=None, max_length=500)
    rule: str = Field(..., min_length=3, max_length=200)
    first_run_at: datetime
    advance_minutes: int = Field(default=0, ge=0, le=10080)
    channel: str = Field(default="telegram", max_length=32)
    status: str = Field(default="active", max_length=16)


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    name: str
    description: Optional[str]
    rule: str
    first_run_at: datetime
    advance_minutes: int
    channel: str
    status: str
    created_at: datetime
    updated_at: datetime


class JobRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    period_key: str
    scheduled_at: datetime
    sent_at: Optional[datetime]
    status: str
    created_at: datetime
    updated_at: datetime


class ConfirmationCreate(BaseModel):
    job_run_id: int
    action: str = Field(..., max_length=16)
    idempotency_key: str = Field(..., min_length=1, max_length=120)
    payload: Optional[dict] = None


class ConfirmationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_run_id: int
    action: str
    confirmed_at: datetime
    idempotency_key: str
    payload: Optional[dict]
    created_at: datetime
    updated_at: datetime


@router.post("/jobs", status_code=201, response_model=JobOut)
def create_job(
    payload: JobCreate,
    db: Session = Depends(get_db),
    user_id: int = Depends(resolve_user_id),
) -> JobOut:
    if payload.channel != "telegram":
        raise HTTPException(status_code=422, detail="unsupported_channel")
    if payload.status not in {"active", "paused", "archived"}:
        raise HTTPException(status_code=422, detail="invalid_status")

    now = _now()
    job = SchedulerJob(
        user_id=user_id,
        name=payload.name,
        description=payload.description,
        rule=payload.rule,
        first_run_at=payload.first_run_at,
        advance_minutes=payload.advance_minutes,
        channel=payload.channel,
        status=payload.status,
        created_at=now,
        updated_at=now,
    )
    db.add(job)
    db.flush()

    run = SchedulerJobRun(
        job_id=job.id,
        period_key=_period_key(payload.first_run_at),
        scheduled_at=payload.first_run_at,
        sent_at=None,
        status="pending",
        created_at=now,
        updated_at=now,
    )
    db.add(run)
    db.commit()
    db.refresh(job)
    return job


@router.get("/jobs", response_model=List[JobOut])
def list_jobs(
    db: Session = Depends(get_db),
    user_id: int = Depends(resolve_user_id),
) -> List[JobOut]:
    return (
        db.query(SchedulerJob)
        .filter(SchedulerJob.user_id == user_id)
        .order_by(SchedulerJob.id.desc())
        .all()
    )


@router.get("/job-runs", response_model=List[JobRunOut])
def list_job_runs(
    status: Optional[str] = Query(default=None, max_length=32),
    from_ts: Optional[datetime] = Query(default=None, alias="from"),
    to_ts: Optional[datetime] = Query(default=None, alias="to"),
    db: Session = Depends(get_db),
    user_id: int = Depends(resolve_user_id),
) -> List[JobRunOut]:
    query = (
        db.query(SchedulerJobRun)
        .join(SchedulerJob, SchedulerJobRun.job_id == SchedulerJob.id)
        .filter(SchedulerJob.user_id == user_id)
    )
    if status:
        query = query.filter(SchedulerJobRun.status == status)
    if from_ts:
        query = query.filter(SchedulerJobRun.scheduled_at >= from_ts)
    if to_ts:
        query = query.filter(SchedulerJobRun.scheduled_at <= to_ts)
    return query.order_by(SchedulerJobRun.scheduled_at.desc()).all()


@router.post("/confirmations", status_code=201, response_model=ConfirmationOut)
def create_confirmation(
    payload: ConfirmationCreate,
    db: Session = Depends(get_db),
    user_id: int = Depends(resolve_user_id),
) -> ConfirmationOut:
    if payload.action not in {"complete", "skip", "snooze", "cancel"}:
        raise HTTPException(status_code=422, detail="invalid_action")

    run = _require_job_run(payload.job_run_id, user_id, db)
    existing = (
        db.query(SchedulerConfirmation)
        .filter(
            SchedulerConfirmation.job_run_id == payload.job_run_id,
            SchedulerConfirmation.idempotency_key == payload.idempotency_key,
        )
        .first()
    )
    if existing:
        return existing

    now = _now()
    confirmation = SchedulerConfirmation(
        job_run_id=payload.job_run_id,
        action=payload.action,
        confirmed_at=now,
        idempotency_key=payload.idempotency_key,
        payload=payload.payload,
        created_at=now,
        updated_at=now,
    )
    db.add(confirmation)

    if payload.action == "complete":
        run.status = "confirmed"
    elif payload.action == "skip":
        run.status = "skipped"
    elif payload.action == "snooze":
        run.status = "snoozed"
    elif payload.action == "cancel":
        run.status = "cancelled"
    run.updated_at = now

    db.commit()
    db.refresh(confirmation)
    return confirmation
