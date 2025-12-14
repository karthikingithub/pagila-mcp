#!/usr/bin/env python3
"""Simple MCP inspector for the pagila MCP server.

Features:
- Start the `mcp_pagila_server.py` as a subprocess (same Python executable).
- Send single or multiple JSON requests and print pretty JSON responses.
- Interactive REPL for quick testing of methods: list_films, run_pagila_query, or raw JSON.

Usage examples:
  # one-shot: list first 5 films
  python mcp_inspector.py -c "list_films 5"

  # interactive
  python mcp_inspector.py
  > list_films 5
  > run SELECT title FROM film LIMIT 2
  > raw {"id":1,"method":"list_films","params":{"limit":5}}
  > quit
"""
from __future__ import annotations

import argparse
import os
import json
import subprocess
import sys
import threading
from typing import Optional


def start_server(python_executable: str = None) -> subprocess.Popen:
    # Prefer workspace virtualenv python if present
    if python_executable is None:
        venv_python = os.path.join(os.getcwd(), ".venv", "bin", "python")
        if os.path.exists(venv_python):
            python_executable = venv_python
        else:
            python_executable = sys.executable

    cmd = [python_executable, "mcp_pagila_server.py"]
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    # thread to forward stderr from server to our stderr with a prefix
    def _stderr_reader():
        assert proc.stderr is not None
        for line in proc.stderr:
            sys.stderr.write("[server-stderr] " + line)

    t = threading.Thread(target=_stderr_reader, daemon=True)
    t.start()
    return proc


def send_request(proc: subprocess.Popen, request: dict) -> Optional[dict]:
    assert proc.stdin is not None and proc.stdout is not None
    line = json.dumps(request, default=str) + "\n"
    proc.stdin.write(line)
    proc.stdin.flush()

    # read one line response
    resp_line = proc.stdout.readline()
    if not resp_line:
        return None
    try:
        return json.loads(resp_line)
    except Exception:
        print("Failed to parse server response:\n", resp_line)
        return None


def pretty_print(obj: object) -> None:
    print(json.dumps(obj, indent=2, default=str))


def repl(proc: subprocess.Popen) -> None:
    print("MCP inspector REPL. Type 'help' for commands.")
    while True:
        try:
            s = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not s:
            continue
        if s in ("q", "quit", "exit"):
            break
        if s == "help":
            print(
                "Commands:\n  list_films <limit>\n  run <SQL SELECT>\n  text2sql <natural language>\n  raw <JSON request>\n  quit"
            )
            continue

        if s.startswith("list_films"):
            parts = s.split(None, 1)
            limit = int(parts[1]) if len(parts) > 1 else 10
            req = {"id": 1, "method": "list_films", "params": {"limit": limit}}
            resp = send_request(proc, req)
            pretty_print(resp)
            continue

        if s.startswith("text2sql "):
            text = s[len("text2sql ") :]
            req = {
                "id": 1,
                "method": "text_to_sql",
                "params": {"text": text, "execute": False},
            }
            resp = send_request(proc, req)
            pretty_print(resp)
            continue

        if s.startswith("raw "):
            js = s[len("raw ") :]
            # Be tolerant of shell-escaped JSON like: {\"id\":1,...}
            req = None
            parse_attempts = [js, js.replace('\\"', '"')]
            if js.startswith("'") and js.endswith("'"):
                parse_attempts.append(js[1:-1])
            for candidate in parse_attempts:
                try:
                    req = json.loads(candidate)
                    break
                except Exception:
                    continue
            if req is None:
                print(
                    'Invalid JSON for raw command. Try: raw {"id":1,...} or use proper shell quoting.'
                )
                continue
            resp = send_request(proc, req)
            pretty_print(resp)
            continue

        print("Unknown command. Type 'help'.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-c",
        "--command",
        help="one-shot command: e.g. 'list_films 5' or 'run SELECT ...' or raw JSON starting with 'raw {...}'",
    )
    args = parser.parse_args()

    proc = start_server()
    try:
        if args.command:
            s = args.command.strip()
            if s.startswith("raw "):
                js = s[len("raw ") :]
                # tolerant parsing for shell-escaped JSON
                req = None
                parse_attempts = [js, js.replace('\\"', '"')]
                if js.startswith("'") and js.endswith("'"):
                    parse_attempts.append(js[1:-1])
                for candidate in parse_attempts:
                    try:
                        req = json.loads(candidate)
                        break
                    except Exception:
                        continue
                if req is None:
                    print(
                        'Invalid JSON for raw command. Try using proper quoting, e.g. -c \'raw {"id":1,...}\' or -c "raw {"id":1,...}"'
                    )
                    return 2
            elif s.startswith("list_films"):
                parts = s.split(None, 1)
                limit = int(parts[1]) if len(parts) > 1 else 10
                req = {"id": 1, "method": "list_films", "params": {"limit": limit}}
            elif s.startswith("text2sql "):
                text = s[len("text2sql ") :]
                req = {
                    "id": 1,
                    "method": "text_to_sql",
                    "params": {"text": text, "execute": False},
                }
            elif s.startswith("run "):
                query = s[len("run ") :]
                req = {
                    "id": 1,
                    "method": "run_pagila_query",
                    "params": {"query": query},
                }
            else:
                print("Unknown one-shot command")
                return 2

            resp = send_request(proc, req)
            pretty_print(resp)
            return 0

        # interactive
        repl(proc)
        return 0
    finally:
        try:
            proc.stdin.close()  # type: ignore[union-attr]
        except Exception:
            pass
        proc.terminate()
        proc.wait(timeout=2)


if __name__ == "__main__":
    raise SystemExit(main())
