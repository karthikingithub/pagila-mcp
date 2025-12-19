#!/usr/bin/env python3
"""
Streamlit UI for the Pagila MCP server.

Features:
- Starts local MCP server subprocess (same protocol as mcp_inspector).
- Chat-style UI with sample NLP prompts that call the server's `text_to_sql`
  and `run_pagila_query` methods.
- Show generated SQL and optional execution results (tables).
- Minimal, professional layout; runs locally.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from queue import Queue
from typing import Optional

import streamlit as st


def _start_server() -> tuple[subprocess.Popen, Queue]:
    venv_python = os.path.join(os.getcwd(), ".venv", "bin", "python")
    python_exe = venv_python if os.path.exists(venv_python) else sys.executable
    cmd = [python_exe, "mcp_pagila_server.py"]
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    stderr_q: Queue = Queue()

    def _forward_stderr():
        assert proc.stderr is not None
        for ln in proc.stderr:
            line = ln.rstrip("\n")
            # keep server logs visible in console for local debugging
            print("[mcp-server-stderr] " + line, file=sys.stderr)
            try:
                stderr_q.put_nowait(line)
            except Exception:
                pass

    t = threading.Thread(target=_forward_stderr, daemon=True)
    t.start()
    return proc, stderr_q


def _send_request(
    proc: subprocess.Popen, request: dict, timeout: float = 10.0
) -> Optional[dict]:
    assert proc.stdin is not None and proc.stdout is not None
    line = json.dumps(request, default=str) + "\n"
    try:
        proc.stdin.write(line)
        proc.stdin.flush()
    except Exception as exc:
        st.error(f"Failed to write to MCP server stdin: {exc}")
        return None

    try:
        resp_line = proc.stdout.readline()
        if not resp_line:
            st.error("MCP server closed stdout or exited")
            return None
        return json.loads(resp_line)
    except Exception as exc:
        st.error(f"Failed to read/parse MCP response: {exc}")
        return None


def _fmt_relative(ts: float) -> str:
    """Format a timestamp as a relative string (e.g. '2m ago')."""
    try:
        now = time.time()
        diff = int(now - float(ts))
    except Exception:
        return ""
    if diff < 5:
        return "just now"
    if diff < 60:
        return f"{diff}s ago"
    minutes = diff // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 48:
        return f"{hours}h ago"
    days = hours // 24
    return f"{days}d ago"


# --- Streamlit UI
st.set_page_config(page_title="Pagila MCP Chat", layout="wide")
st.title("Pagila MCP — Chat UI")
st.caption(
    "Local chat-like UI that generates and optionally executes SQL via the MCP server."
)

# ensure server subprocess in session state
if "mcp_proc" not in st.session_state:
    proc, stderr_q = _start_server()
    st.session_state.mcp_proc = proc
    st.session_state.mcp_stderr_q = stderr_q
    st.session_state.history = []

    # monitor thread posts events into stderr queue for main thread handling
    def _monitor_loop():
        while True:
            proc_ref = st.session_state.get("mcp_proc")
            if proc_ref is None:
                time.sleep(1)
                continue
            try:
                if proc_ref.poll() is not None:
                    try:
                        st.session_state.mcp_stderr_q.put_nowait(
                            f"EVENT:EXIT:{proc_ref.returncode}"
                        )
                    except Exception:
                        pass
            except Exception:
                pass
            time.sleep(1)

    mon = threading.Thread(target=_monitor_loop, daemon=True)
    mon.start()


# Sidebar
with st.sidebar:
    st.header("Samples")
    samples = [
        "Show film titles from 2010 limit 3",
        "List movie titles that contain 'love' limit 5",
        "Show title and rental_rate for films from 2005",
        "Give me titles released in 2012",
    ]
    for s in samples:
        if st.button(s):
            st.session_state._pending_sample = s
            st.session_state._pending_execute = True

    st.markdown("---")
    st.header("Options")
    execute_sql = st.checkbox("Execute generated SQL", value=False)
    auto_exec_confident = st.checkbox(
        "Auto-execute only if confident",
        value=True,
        help="Only auto-run generated SQL when the generator reports high confidence",
    )
    st.info("When checked, `text_to_sql` results will be executed and rows returned.")
    st.markdown("---")

    st.write("Server status:")
    proc = st.session_state.mcp_proc
    stderr_q = st.session_state.get("mcp_stderr_q")
    running = proc.poll() is None
    st.write("PID: %s — Running: %s" % (getattr(proc, "pid", None), running))
    if st.button("Restart server"):
        try:
            if proc and proc.poll() is None:
                proc.terminate()
        except Exception:
            pass
        new_proc, new_q = _start_server()
        st.session_state.mcp_proc = new_proc
        st.session_state.mcp_stderr_q = new_q
        st.success("Server restarted")

    st.markdown("**Server stderr (recent):**")
    if "mcp_failure_count" not in st.session_state:
        st.session_state.mcp_failure_count = 0
        st.session_state.mcp_restart_backoff_until = 0.0
        st.session_state.mcp_needs_restart = False

    human_lines = []
    if stderr_q:
        lines = []
        try:
            while len(lines) < 200:
                lines.append(stderr_q.get_nowait())
        except Exception:
            pass
        for ln in lines:
            if isinstance(ln, str) and ln.startswith("EVENT:EXIT:"):
                try:
                    code = int(ln.split(":")[-1])
                except Exception:
                    code = None
                st.session_state.mcp_failure_count = (
                    st.session_state.get("mcp_failure_count", 0) + 1
                )
                now = time.time()
                attempts = st.session_state.mcp_failure_count
                backoff = min(300, 2**attempts)
                st.session_state.mcp_restart_backoff_until = now + backoff
                st.session_state.mcp_needs_restart = True
                human_lines.append(
                    f"MCP server exited (code={code}); backoff {backoff}s"
                )
            else:
                human_lines.append(str(ln))

        if human_lines:
            for ln in human_lines[-20:]:
                st.text(ln)
        else:
            st.write("(no recent server stderr)")
    else:
        st.write("(no server stderr queue)")

    if st.session_state.get("mcp_needs_restart"):
        backoff_until = st.session_state.get("mcp_restart_backoff_until", 0)
        now = time.time()
        if now < backoff_until:
            diff = int(backoff_until - now)
            st.warning(
                (
                    f"Server exited; restart allowed in {diff}s. "
                    f"(failures={st.session_state.get('mcp_failure_count')})"
                )
            )
            if st.button("Force restart now (override backoff)"):
                proc = st.session_state.get("mcp_proc")
                try:
                    if proc and proc.poll() is None:
                        proc.terminate()
                except Exception:
                    pass
                new_proc, new_q = _start_server()
                st.session_state.mcp_proc = new_proc
                st.session_state.mcp_stderr_q = new_q
                st.session_state.mcp_needs_restart = False
                st.session_state.mcp_failure_count = 0
                st.success("Server force-restarted")
        else:
            st.warning(
                (
                    "Server exited; restart available now. "
                    f"(failures={st.session_state.get('mcp_failure_count')})"
                )
            )
            if st.button("Restart server now"):
                proc = st.session_state.get("mcp_proc")
                try:
                    if proc and proc.poll() is None:
                        proc.terminate()
                except Exception:
                    pass
                new_proc, new_q = _start_server()
                st.session_state.mcp_proc = new_proc
                st.session_state.mcp_stderr_q = new_q
                st.session_state.mcp_needs_restart = False
                st.session_state.mcp_failure_count = 0
                st.success("Server restarted")


# main chat column
col1, col2 = st.columns([3, 2])
with col1:
    st.subheader("Conversation")

    # input area (placed at the top so it's always visible)
    # handle pending sample injection
    if "_pending_sample" in st.session_state:
        pending = st.session_state.pop("_pending_sample")
        sample_exec = st.session_state.pop("_pending_execute", False)
        st.session_state["chat_input"] = pending
    else:
        sample_exec = False

    user_input = st.text_input(
        "Enter natural language query (or SQL with `run:` prefix):", key="chat_input"
    )
    submit = st.button("Send")

    if submit and user_input:
        st.session_state.history.append(
            {"role": "user", "text": user_input, "ts": time.time()}
        )
        # immediate handling (run: path or NLP path)
        if user_input.lower().strip().startswith("run:"):
            sql = user_input.split(":", 1)[1].strip()
            req = {"id": 1, "method": "run_pagila_query", "params": {"query": sql}}
            resp = _send_request(st.session_state.mcp_proc, req)
            if resp is None:
                st.session_state.history.append(
                    {
                        "role": "assistant",
                        "text": "No response from MCP server.",
                        "ts": time.time(),
                    }
                )
            else:
                result = resp.get("result") if isinstance(resp, dict) else None
                error = resp.get("error") if isinstance(resp, dict) else None
                rows = (
                    result.get("rows")
                    if isinstance(result, dict) and "rows" in result
                    else None
                )
                meta = {"sql": sql}
                if rows is not None:
                    meta["rows"] = rows
                if error:
                    meta["error"] = error
                st.session_state.history.append(
                    {
                        "role": "assistant",
                        "text": "Executed SQL",
                        "meta": meta,
                        "ts": time.time(),
                    }
                )
        else:
            desired_execute = execute_sql or sample_exec
            gen_req = {
                "id": 1,
                "method": "text_to_sql",
                "params": {"text": user_input, "execute": False, "provider": "local"},
            }
            resp = _send_request(st.session_state.mcp_proc, gen_req)
            if resp is None:
                st.session_state.history.append(
                    {
                        "role": "assistant",
                        "text": "No response from MCP server.",
                        "ts": time.time(),
                    }
                )
            else:
                res = resp.get("result", resp)
                sql = res.get("sql") if isinstance(res, dict) else None
                params = res.get("params") if isinstance(res, dict) else None
                note = res.get("note") if isinstance(res, dict) else None
                confident = (
                    res.get("confident", True) if isinstance(res, dict) else True
                )

                if not confident:
                    st.session_state.history.append(
                        {
                            "role": "assistant",
                            "text": (
                                "Generator not confident — please review/modify "
                                "the SQL or run your own SQL using the `run:` prefix."
                            ),
                            "meta": {"confident": False},
                            "ts": time.time(),
                        }
                    )
                else:
                    st.session_state.history.append(
                        {
                            "role": "assistant",
                            "text": note or "Generated SQL",
                            "meta": {
                                "sql": sql,
                                "rows": None,
                                "params": params,
                                "confident": confident,
                            },
                            "ts": time.time(),
                        }
                    )
                    if desired_execute:
                        exec_req = {
                            "id": 1,
                            "method": "execute_sql",
                            "params": {"sql": sql, "params": params},
                        }
                        exec_resp = _send_request(st.session_state.mcp_proc, exec_req)
                        if exec_resp is None:
                            st.session_state.history.append(
                                {
                                    "role": "assistant",
                                    "text": "No response from MCP server on execute.",
                                    "ts": time.time(),
                                }
                            )
                        else:
                            exec_res = exec_resp.get("result", exec_resp)
                            rows = (
                                exec_res.get("rows")
                                if isinstance(exec_res, dict)
                                else None
                            )
                            exec_note = (
                                exec_res.get("note")
                                if isinstance(exec_res, dict)
                                else None
                            )
                            last = st.session_state.history[-1]
                            last_meta = last.setdefault("meta", {})
                            last_meta["rows"] = rows
                            if exec_note:
                                last_meta["note"] = exec_note

    # Sort history by timestamp (ascending) to get chronological order,
    # then group into user-first blocks. This avoids cases where timestamps
    # or list ordering produce assistant-before-user rendering.
    sorted_hist = sorted(st.session_state.history, key=lambda m: m.get("ts", 0))
    blocks: list[list[dict]] = []
    current: list[dict] = []
    for m in sorted_hist:
        if m.get("role") == "user":
            if current:
                blocks.append(current)
            current = [m]
        else:
            if not current:
                current = [m]
            else:
                current.append(m)
    if current:
        blocks.append(current)

    # render newest block first
    for block in reversed(blocks):
        for msg in block:
            role = msg.get("role")
            text = msg.get("text")
            meta = msg.get("meta", {})
            ts = msg.get("ts")
        # separator and relative timestamp
        st.markdown("---")
        if ts:
            st.caption(_fmt_relative(ts))

        # lightweight avatar using native Streamlit columns (faster than HTML)
        av_col, msg_col = st.columns([0.07, 0.93])
        with av_col:
            if role == "user":
                st.markdown("**You**")
            else:
                st.markdown("**AI**")
        with msg_col:
            # render message text plainly (faster); preserve code blocks below
            try:
                st.write(text)
            except Exception:
                st.text(text)

        if meta.get("sql"):
            st.code(meta["sql"], language="sql")
        if meta.get("note"):
            st.info(meta.get("note"))
        if meta.get("error"):
            st.error(meta.get("error"))
        if meta.get("rows"):
            try:
                st.dataframe(meta["rows"])
            except Exception:
                st.write(meta["rows"])

with col2:
    st.subheader("Details / Last response")
    if st.session_state.history:
        last = st.session_state.history[-1]
        st.json(last, expanded=False)
    else:
        st.write("No messages yet.")

st.markdown("---")
st.markdown("Local run: `python -m streamlit run streamlit_app.py`")


def _cleanup():
    proc = st.session_state.get("mcp_proc")
    if proc and proc.poll() is None:
        try:
            proc.terminate()
        except Exception:
            pass
