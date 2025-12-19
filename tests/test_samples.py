import asyncio

import pytest

from mcp_pagila_server import handle_run_pagila_query, handle_text_to_sql

SAMPLES = [
    "Show film titles from 2010 limit 3",
    "List movie titles that contain 'love' limit 5",
    "Show title and rental_rate for films from 2005",
    "Give me titles released in 2012",
]


@pytest.mark.parametrize("text", SAMPLES)
def test_text_to_sql_generates_and_executes(text):
    # call the async handler directly; it will use the DB configured via config.env
    res = asyncio.run(
        handle_text_to_sql({"text": text, "execute": True, "provider": "local"})
    )
    assert isinstance(res, dict)
    assert "sql" in res and isinstance(res["sql"], str)
    # when execute=True we expect rows key
    assert "rows" in res
    assert isinstance(res["rows"], list)
    # expect at least 0 rows (DB may return 0 for some queries), but ensure no error
    assert "error" not in res


def test_forbidden_raw_queries_rejected():
    # DROP statement should be rejected
    with pytest.raises(ValueError):
        asyncio.run(handle_run_pagila_query({"query": "DROP TABLE film"}))


def test_multiple_statements_rejected():
    with pytest.raises(ValueError):
        asyncio.run(handle_run_pagila_query({"query": "SELECT 1; SELECT 2"}))


def test_truncation_note(monkeypatch):
    # set max rows to 2 and request more rows; expect note present
    monkeypatch.setenv("MCP_MAX_ROWS", "2")
    res = asyncio.run(
        handle_run_pagila_query({"query": "SELECT title FROM film LIMIT 5"})
    )
    assert isinstance(res, dict)
    assert "rows" in res
    assert len(res["rows"]) <= 2
    assert "note" in res
