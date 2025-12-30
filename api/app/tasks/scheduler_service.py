from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

load_dotenv()

API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000/v1").rstrip("/")
FX_CRON_SCHEDULE = os.getenv("FX_CRON_SCHEDULE", "0 9 * * *")
FX_TIMEOUT_SEC = float(os.getenv("FX_TIMEOUT_SECONDS", "10"))
FX_SYNC_ON_START = os.getenv("FX_SYNC_ON_START", "false").lower() in ("1", "true", "yes")


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


def main() -> None:
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(_sync_fx_once, CronTrigger.from_crontab(FX_CRON_SCHEDULE), id="fx-sync")
    scheduler.start()

    loop = asyncio.get_event_loop()
    if FX_SYNC_ON_START:
        loop.create_task(_sync_fx_once())
    try:
        loop.run_forever()
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()


if __name__ == "__main__":
    main()
