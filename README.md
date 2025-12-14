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