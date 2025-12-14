import os
import logging
from contextlib import contextmanager
from typing import Any, Iterable
import time

from psycopg import connect, OperationalError, DatabaseError
from psycopg.rows import dict_row
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv("config.env")


def get_db_params() -> dict[str, Any]:
    return {
        "host": os.getenv("PG_HOST", "localhost"),
        "port": int(os.getenv("PG_PORT", "5432")),
        "dbname": os.getenv("PG_DB", "pagila"),
        "user": os.getenv("PG_USER", "postgres"),
        "password": os.getenv("PG_PASSWORD", ""),
    }


@contextmanager
def get_connection():
    params = get_db_params()
    try:
        logger.debug(
            "Opening DB connection to %s:%s/%s",
            params["host"],
            params["port"],
            params["dbname"],
        )
        conn = connect(**params)
        yield conn
    except OperationalError as exc:
        logger.error("DB connection failed: %s", exc, exc_info=True)
        raise
    finally:
        try:
            conn.close()  # type: ignore[name-defined]
            logger.debug("DB connection closed")
        except Exception:
            pass


def run_query(query: str, params: Iterable[Any] | None = None):
    with get_connection() as conn:
        try:
            with conn.cursor(row_factory=dict_row) as cur:
                logger.debug("Executing query: %s params=%s", query, params)
                start = time.monotonic()
                cur.execute(query, tuple(params or ()))
                rows = cur.fetchall()
                duration = time.monotonic() - start
                logger.info(
                    "Query executed rows=%d duration=%.3fs",
                    len(rows) if isinstance(rows, list) else -1,
                    duration,
                )
                return rows
        except DatabaseError as exc:
            logger.error("Error executing query: %s", exc, exc_info=True)
            raise
