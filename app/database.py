"""
数据库引擎、会话工厂、FastAPI 依赖注入。
从 main.py 中抽取，供 auth.py 和 main.py 共享引用。
"""

import time
import logging

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import OperationalError

from config import settings

logger = logging.getLogger("fee_claims")

# ── 引擎（带重试） ──────────────────────────────────────
MAX_DB_RETRIES = 3
RETRY_DELAY_SECONDS = 2


def _create_engine_with_retry():
    last_exc = None
    for attempt in range(1, MAX_DB_RETRIES + 1):
        try:
            engine = create_engine(
                settings.database_url,
                pool_size=10,
                max_overflow=20,
                pool_pre_ping=True,
                pool_recycle=3600,
                echo=False,
            )
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("数据库连接成功")
            return engine
        except Exception as exc:
            last_exc = exc
            logger.warning(f"数据库连接失败 (第 {attempt}/{MAX_DB_RETRIES} 次): {exc}")
            if attempt < MAX_DB_RETRIES:
                time.sleep(RETRY_DELAY_SECONDS)
    raise last_exc


engine = _create_engine_with_retry()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Session:
    """FastAPI 依赖注入：获取数据库会话。"""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
