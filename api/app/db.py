from __future__ import annotations

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base


_DATABASE_URL_ENV = (os.getenv("DATABASE_URL") or "").strip()
DATABASE_URL = _DATABASE_URL_ENV or "postgresql://flow_ledger:flow_ledger@db:5432/flow_ledger"

engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

Base = declarative_base()
