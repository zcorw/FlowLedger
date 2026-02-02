from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import SchedulerJob, SchedulerJobRun, SchedulerReminder, User

load_dotenv()

API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000/v1").rstrip("/")
FX_CRON_SCHEDULE = os.getenv("FX_CRON_SCHEDULE", "0 9 * * *")
FX_TIMEOUT_SEC = float(os.getenv("FX_TIMEOUT_SECONDS", "10"))
FX_SYNC_ON_START = os.getenv("FX_SYNC_ON_START", "false").lower() in ("1", "true", "yes")
SCHEDULER_SCAN_CRON = os.getenv("SCHEDULER_SCAN_CRON", "*/1 * * * *")
SCHEDULER_BATCH_SIZE = int(os.getenv("SCHEDULER_BATCH_SIZE", "100"))
BOT_INTERNAL_URL = os.getenv("BOT_INTERNAL_URL", "http://bot:7090").rstrip("/")
BOT_INTERNAL_TOKEN = os.getenv("BOT_INTERNAL_TOKEN", "").strip()
BOT_INTERNAL_TIMEOUT = float(os.getenv("BOT_INTERNAL_TIMEOUT_SECONDS", "5"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _sync_fx_once() -> None:
    url = f"{API_BASE_URL}/exchange-rates/sync"
    try:
        async with httpx.AsyncClient(timeout=FX_TIMEOUT_SEC) as client:
            resp = await client.post(url)
            resp.raise_for_status()
            print(f"[scheduler] {_now()} sync ok status={resp.status_code}")
    except Exception as exc:  # noqa: BLE001
        print(f"[scheduler] {_now()} sync failed: {exc}")


def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _period_key(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M")


def _parse_cron_rule(rule: str) -> CronTrigger | None:
    rule = (rule or "").strip()
    if rule.startswith("cron:"):
        expr = rule.split(":", 1)[1].strip()
        if not expr:
            return None
        return CronTrigger.from_crontab(expr, timezone=timezone.utc)
    if rule.startswith("cron "):
        expr = rule.split(" ", 1)[1].strip()
        if not expr:
            return None
        return CronTrigger.from_crontab(expr, timezone=timezone.utc)
    return None


def _ensure_job_runs(job: SchedulerJob, db: Session, now: datetime) -> None:
    last_run = (
        db.query(SchedulerJobRun)
        .filter(SchedulerJobRun.job_id == job.id)
        .order_by(SchedulerJobRun.scheduled_at.desc())
        .first()
    )
    if not last_run:
        if job.first_run_at <= now:
            run = SchedulerJobRun(
                job_id=job.id,
                period_key=_period_key(job.first_run_at),
                scheduled_at=job.first_run_at,
                sent_at=None,
                status="pending",
                created_at=now,
                updated_at=now,
            )
            db.add(run)
        return

    trigger = _parse_cron_rule(job.rule)
    if not trigger:
        return

    next_time = trigger.get_next_fire_time(last_run.scheduled_at, last_run.scheduled_at)
    created = 0
    while next_time and next_time <= now and created < 100:
        run = SchedulerJobRun(
            job_id=job.id,
            period_key=_period_key(next_time),
            scheduled_at=next_time,
            sent_at=None,
            status="pending",
            created_at=now,
            updated_at=now,
        )
        db.add(run)
        created += 1
        next_time = trigger.get_next_fire_time(next_time, next_time)


async def _send_bot_notification(telegram_user_id: int, text: str) -> bool:
    headers = {}
    if BOT_INTERNAL_TOKEN:
        headers["X-Internal-Token"] = BOT_INTERNAL_TOKEN
    payload = {"telegram_user_id": telegram_user_id, "text": text}
    try:
        async with httpx.AsyncClient(timeout=BOT_INTERNAL_TIMEOUT) as client:
            resp = await client.post(f"{BOT_INTERNAL_URL}/internal/notify", json=payload, headers=headers)
            resp.raise_for_status()
            return True
    except Exception as exc:  # noqa: BLE001
        print(f"[scheduler] {_now()} notify failed: {exc}")
        return False


async def _scan_and_notify() -> None:
    now = _now_dt()
    db = SessionLocal()
    try:
        jobs = (
            db.query(SchedulerJob)
            .filter(SchedulerJob.status == "active", SchedulerJob.channel == "telegram")
            .order_by(SchedulerJob.id.asc())
            .all()
        )
        for job in jobs:
            _ensure_job_runs(job, db, now)
        db.commit()

        candidates = (
            db.query(SchedulerJobRun, SchedulerJob, User)
            .join(SchedulerJob, SchedulerJobRun.job_id == SchedulerJob.id)
            .join(User, SchedulerJob.user_id == User.id)
            .filter(
                SchedulerJob.status == "active",
                SchedulerJob.channel == "telegram",
                SchedulerJobRun.status == "pending",
                User.telegram_user_id.isnot(None),
                User.is_bot_enabled.is_(True),
            )
            .order_by(SchedulerJobRun.scheduled_at.asc())
            .limit(SCHEDULER_BATCH_SIZE)
            .all()
        )

        for run, job, user in candidates:
            due_at = run.scheduled_at - timedelta(minutes=job.advance_minutes)
            if due_at > now:
                continue
            text = (
                f"任务提醒：{job.name}\n"
                f"任务说明：{job.description or '(无)'}\n"
                f"计划时间(UTC)：{run.scheduled_at.isoformat(timespec='minutes')}\n"
                f"任务ID：{job.id} / 实例ID：{run.id}"
            )
            ok = await _send_bot_notification(int(user.telegram_user_id), text)
            if not ok:
                continue
            run.sent_at = now
            run.status = "sent"
            run.updated_at = now
            reminder = SchedulerReminder(
                job_run_id=run.id,
                sent_at=now,
                payload={"channel": "telegram", "text": text},
                created_at=now,
                updated_at=now,
            )
            db.add(reminder)
        db.commit()
    finally:
        db.close()


def main() -> None:
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(_sync_fx_once, CronTrigger.from_crontab(FX_CRON_SCHEDULE), id="fx-sync")
    scheduler.add_job(_scan_and_notify, CronTrigger.from_crontab(SCHEDULER_SCAN_CRON), id="scheduler-scan")
    scheduler.start()

    loop = asyncio.get_event_loop()
    if FX_SYNC_ON_START:
        loop.create_task(_sync_fx_once())
    loop.create_task(_scan_and_notify())
    try:
        loop.run_forever()
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()


if __name__ == "__main__":
    main()
