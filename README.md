# Pagila MCP — Local Streamlit Chat

Minimal local UI and MCP server for experimenting with natural-language → SQL generation and execution against a local Pagila Postgres instance.

Quick start
1. Copy the example env and fill in real DB credentials (do NOT commit your real `config.env`):

   cp config.env.example config.env
   # edit config.env and set PG_USER / PG_PASSWORD etc.

2. Create a virtualenv and install deps (recommended):

   python -m venv .venv
   .venv/bin/python -m pip install -r requirements.txt

3. Run Streamlit UI:

   .venv/bin/python -m streamlit run streamlit_app.py

Notes
- `config.env` is git-ignored. Keep secrets out of git and use `config.env.example` for documentation.
- The app starts `mcp_pagila_server.py` as a subprocess and communicates via JSON-lines.
- Tests are available under `tests/` and can be run with:

  .venv/bin/python -m pytest -q

If you want help adding CI or removing secrets from git history, tell me and I can prepare a workflow or a safe git-filter-repo script.
# pagila-mcp

Lightweight MCP (Model Context Protocol) server and local UI for the Pagila sample Postgres database.

This repository provides a small JSON-RPC-like MCP server that accepts requests on stdin and writes JSON responses on stdout. It includes a minimal Streamlit chat UI that generates SQL from natural language (local heuristic) and can safely execute parameterized SQL against the configured Postgres instance.

Contents
- `mcp_pagila_server.py` — the MCP server. Exposes handlers such as:
  - `text_to_sql` — generates parameterized SELECT SQL from natural language using a local heuristic. Returns `{sql, params, note, confident}`.
  - `execute_sql` — safely execute parameterized SQL (sql + params) and return rows and notes.
  - `run_pagila_query` — limited path to execute raw `SELECT` SQL (validated, single-statement, row-cap enforced).
- `db.py` — DB helpers and a safe `run_query` wrapper.
- `streamlit_app.py` — Streamlit chat UI to generate and optionally execute SQL. Starts the MCP server subprocess and renders stderr/logs and results.
- `mcp_inspector.py` — small interactive inspector for quick manual requests.
- `tests/` — pytest suite covering NL→SQL samples and safety checks.
- `logs/pagila.log` — rotating log file for server logs (created at runtime).

Quickstart
1. Copy the example env and set your DB credentials:

```bash
cp config.env.example config.env
# edit config.env and set PG_HOST, PG_USER, PG_PASSWORD, PG_DB, etc.
```

2. Create a virtualenv and install dependencies:

```bash
python -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
```

3. Run the Streamlit chat UI (recommended for trying the app):

```bash
.venv/bin/python -m streamlit run streamlit_app.py
```

Streamlit UI notes
- The app launches the MCP server as a subprocess and shows recent server stderr in the sidebar.
- Conversation is shown newest-first so executed results appear at the top.
- Options in the sidebar:
  - `Execute generated SQL` — whether to run generated SQL automatically.
  - `Auto-execute only if confident` — when checked, the UI will only auto-run SQL if the generator reports `confident: true`.
- If the local generator reports low confidence, the UI will show only a single assistant message:
  `Generator not confident — please review/modify the SQL or run your own SQL using the run: prefix.`
  No SQL is displayed in that case (safety & clarity).

Server behavior and safety
- The local text→SQL generator returns parameterized SQL (placeholders) and a `params` list. The server exposes `execute_sql` which executes the SQL using the provided parameters. This avoids injecting literals containing `%` into SQL execution.
- `run_pagila_query` only accepts a single `SELECT` statement, rejects multiple statements and dangerous keywords (basic blacklist), and applies a row cap (configured via `MCP_MAX_ROWS`) with a returned `note` when results were truncated.
- `db.run_query` was hardened to avoid passing an empty params sequence to psycopg which could cause placeholder parsing errors; it calls `cur.execute(query)` when `params` is falsy.
- JSON serialization: Decimal values are serialized to floats for JSON responses from the server.

Logging
- Server logs are emitted to stderr and also written to `logs/pagila.log` via a rotating file handler. Check the Streamlit sidebar `Server stderr (recent)` for live messages when using the UI.

Testing
- Tests are in `tests/` and use pytest. A small `tests/conftest.py` ensures the project root is on `sys.path` during test runs so top-level modules import correctly.
- Run tests with:

```bash
.venv/bin/python -m pytest -q
```

Development notes
- The generator is a local heuristic (_no external LLMs by default_). It handles common prompts for `film`, `category`, and `actor` and returns a `confident` flag to help the UI decide whether to auto-run SQL.
- The Streamlit UI keeps the server subprocess running for the session and provides restart/backoff controls when the server exits unexpectedly.

Troubleshooting
- If pytest cannot import top-level modules, ensure you run tests from the repository root (the provided `tests/conftest.py` should already handle this for typical runs).
- If you see psycopg errors about `%` placeholders, confirm the `text_to_sql` handler returns a `params` list and that the UI or caller uses `execute_sql` (which sends both `sql` and `params`) instead of sending raw SQL with `%s` tokens.

Next improvements (ideas)
- Expand the heuristic coverage for more tables/phrases and improve confidence scoring.
- Add an option to hide debug metadata in the UI for non-developer users.
- Add CI integration that spins up a disposable Postgres instance for running tests in CI.

License
MIT
# pagila-mcp

Small MCP server wrapper for the Pagila sample database. This repository provides:

- `mcp_pagila_server.py` - MCP server that accepts JSON requests on stdin and returns JSON responses on stdout.
- `db.py` - database helpers to run queries against Postgres.
- `mcp_inspector.py` - a small interactive inspector that starts the server subprocess and sends test requests.

Quickstart
1. Copy the example env and set your DB credentials:

```bash
cp config.env.example config.env
# edit config.env and set PG_HOST, PG_USER, PG_PASSWORD etc.
```

2. Create a virtualenv and install dependencies:

```bash
python -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

3. Run the inspector (it will start the server for you):

```bash
.venv/bin/python mcp_inspector.py
# or one-shot examples
.venv/bin/python mcp_inspector.py -c "list_films 5"
.venv/bin/python mcp_inspector.py -c "text2sql show me film titles from 2010 limit 3"
```

Usage & safety
- The server exposes `run_pagila_query` which accepts only `SELECT` statements. `text_to_sql` generates SELECT SQL from natural language (local heuristic by default).
- Do not commit `config.env` or any secrets. Use environment variables for production.

CI & code style
- This repo includes a GitHub Actions CI workflow at `.github/workflows/ci.yml` to run formatting and tests.
- Use `pre-commit` (configured in `.pre-commit-config.yaml`) to run black/isort/flake8 locally.

License
MIT
# Pagila MCP server

Lightweight MCP server around the Pagila DB.

Quick start:
1. Copy `.env.example` -> `config.env` and fill DB creds.
2. Create a virtualenv and install dependencies:
   ```
   python -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ```
3. Run the server:
   ```
   .venv/bin/python mcp_pagila_server.py
   ```
4. Use the inspector: `.venv/bin/python mcp_inspector.py`

See [.vscode/launch.json](.vscode/launch.json) and [.vscode/mcp.json](.vscode/mcp.json) for examples.