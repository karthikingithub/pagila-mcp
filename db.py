import logging
import os
import time
from contextlib import contextmanager
from typing import Any, Iterable

from dotenv import load_dotenv
from psycopg import DatabaseError, OperationalError, connect
from psycopg.rows import dict_row

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
                # psycopg's execute treats percent-signs in the query as
                # placeholders when a params sequence is provided. If no
                # params are given, call execute(query) to avoid parsing
                # literal %% patterns (for example in ILIKE '%love%').
                if params:
                    cur.execute(query, tuple(params))
                else:
                    cur.execute(query)
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
