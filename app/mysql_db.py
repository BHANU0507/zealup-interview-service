"""
MySQL connection for the zealup_db (User micro-service database).

Environment variables (add to .env):
  MYSQL_HOST     default: localhost
  MYSQL_PORT     default: 3306
  MYSQL_DB       default: zealup_db
  MYSQL_USER     default: bhanu
  MYSQL_PASSWORD default: root
"""

import os
from typing import Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

load_dotenv()

MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_DB   = os.getenv("MYSQL_DB", "zealup_db")
MYSQL_USER = os.getenv("MYSQL_USER", "bhanu")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "root")

# pymysql driver — no C extensions needed
DATABASE_URL = (
    f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}"
    f"@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}"
    f"?charset=utf8mb4"
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,       # auto-reconnect on stale connections
    pool_recycle=300,         # recycle connections every 5 min
    connect_args={"connect_timeout": 10},
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency — yields a DB session and closes it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
