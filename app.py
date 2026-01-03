import hashlib
import json
import os
import subprocess
import sys
import threading
from queue import Queue
from typing import Optional

import chromadb
import google.generativeai as genai
import streamlit as st
from dotenv import load_dotenv

# Set page config at the very top
st.set_page_config(page_title="Pagila SQL Bot", layout="wide")

# 1. Load Environment Variables
load_dotenv("config.env", override=True)
api_key = os.getenv("GEMINI_API_KEY")

# 2. Configure Gemini
if not api_key:
    st.error("GEMINI_API_KEY not found. Please check your .env file.")
    st.stop()

genai.configure(api_key=api_key)


# --- MCP Server Helpers ---
def _start_server() -> tuple[subprocess.Popen, Queue]:
    script_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "mcp_pagila_server.py"
    )
    cmd = [sys.executable, script_path]
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


def _send_request(proc: subprocess.Popen, request: dict) -> Optional[dict]:
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


# Initialize MCP Server in Session State
if "mcp_proc" not in st.session_state:
    proc, stderr_q = _start_server()
    st.session_state.mcp_proc = proc
    st.session_state.mcp_stderr_q = stderr_q

# Initialize Session State for History and Usage
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "token_metrics" not in st.session_state:
    st.session_state.token_metrics = {"input": 0, "output": 0, "total_cost": 0.0}
if "last_executed_sql" not in st.session_state:
    st.session_state.last_executed_sql = None
if "last_execution_success" not in st.session_state:
    st.session_state.last_execution_success = False

# Pricing (USD per 1M tokens) - Approximate
PRICING = {
    "models/gemini-1.5-flash": {"input": 0.075, "output": 0.30},
    "models/gemini-1.5-pro": {"input": 3.50, "output": 10.50},
    "models/gemini-pro": {"input": 0.50, "output": 1.50},
}

STATS_FILE = "usage_stats.json"


def load_global_stats():
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, "r") as f:
                return json.load(f)
        except (IOError, json.JSONDecodeError):
            pass
    return {"input": 0, "output": 0, "total_cost": 0.0}


def save_global_stats(stats):
    with open(STATS_FILE, "w") as f:
        json.dump(stats, f)


# --- Vector DB Setup ---
@st.cache_resource
def get_chroma_client():
    # Persistent storage in 'vector_store' folder
    return chromadb.PersistentClient(path="vector_store")


if "chroma_client" not in st.session_state:
    st.session_state.chroma_client = get_chroma_client()
    st.session_state.sql_collection = (
        st.session_state.chroma_client.get_or_create_collection(name="sql_cache")
    )

if "global_metrics" not in st.session_state:
    st.session_state.global_metrics = load_global_stats()


def get_embedding(text):
    try:
        # Use Gemini's embedding model
        result = genai.embed_content(model="models/text-embedding-004", content=text)
        return result["embedding"]
    except Exception as e:
        st.error(f"Embedding Error: {e}")
        return None


# Sidebar: Model Selection
st.sidebar.header("Settings")
try:
    # Get models that support content generation
    available_models = [
        m.name
        for m in genai.list_models()
        if "generateContent" in m.supported_generation_methods
    ]

    # Determine default index (prefer 1.5-flash, then pro)
    default_model = "models/gemini-1.5-flash"
    if default_model in available_models:
        index = available_models.index(default_model)
    elif "models/gemini-pro" in available_models:
        index = available_models.index("models/gemini-pro")
    else:
        index = 0

    selected_model = st.sidebar.selectbox("Choose Model", available_models, index=index)
except Exception as e:
    st.sidebar.error(f"API Error listing models: {str(e)}")
    selected_model = "gemini-1.5-flash"  # Fallback

# Sidebar: Schema Visualization
st.sidebar.markdown("---")
st.sidebar.header("Schema Info")
if st.sidebar.checkbox("Show Schema Diagram"):
    if os.path.exists("pagila-schema-diagram.png"):
        st.sidebar.image("pagila-schema-diagram.png", caption="Database Schema")
    else:
        st.sidebar.warning("Diagram not found.")


@st.cache_data
def load_metadata():
    if os.path.exists("pagila-metadata.txt"):
        with open("pagila-metadata.txt", "r") as f:
            return f.read()
    return ""


if st.sidebar.checkbox("Show Metadata"):
    st.sidebar.text(load_metadata())

# Sidebar: Usage Metrics
st.sidebar.markdown("---")
st.sidebar.header("Session Usage")
cols = st.sidebar.columns(2)
cols[0].metric("Input Tokens", st.session_state.token_metrics["input"])
cols[1].metric("Output Tokens", st.session_state.token_metrics["output"])
st.sidebar.metric(
    "Est. Cost ($)", f"{st.session_state.token_metrics['total_cost']:.6f}"
)

st.sidebar.markdown("---")
st.sidebar.header("Total History Usage")
cols_g = st.sidebar.columns(2)
cols_g[0].metric("Total Input", st.session_state.global_metrics["input"])
cols_g[1].metric("Total Output", st.session_state.global_metrics["output"])
st.sidebar.metric(
    "Total Cost ($)", f"{st.session_state.global_metrics['total_cost']:.6f}"
)


# 3. Define Tools for Gemini (The "Hands")
def list_tables():
    """
    Retrieves a list of all table names in the database.
    Use this first to understand what data is available.
    """
    req = {"id": "list_tables", "method": "list_tables", "params": {}}
    resp = _send_request(st.session_state.mcp_proc, req)
    if resp and "result" in resp:
        return resp["result"].get("tables", [])
    return []


def get_table_schema(table_names: list[str]):
    """
    Retrieves the schema (columns and data types) for a specific list of tables.
    Use this to understand column names before writing a SQL query.
    """
    req = {
        "id": "get_schema",
        "method": "get_table_schema",
        "params": {"table_names": table_names},
    }
    resp = _send_request(st.session_state.mcp_proc, req)
    if resp and "result" in resp:
        return resp["result"].get("schema_rows", [])
    return []


def execute_sql(query: str):
    """
    Executes a SQL query against the database and returns the results.
    """
    st.session_state.last_executed_sql = query  # Capture for caching
    st.markdown("### Generated SQL")
    st.code(query, language="sql")

    req = {"id": "exec_sql", "method": "run_pagila_query", "params": {"query": query}}
    resp = _send_request(st.session_state.mcp_proc, req)

    if not resp:
        st.error("MCP Server did not respond.")
        st.session_state.last_execution_success = False
        return "Error: MCP Server did not respond."

    if "error" in resp:
        st.error(f"Execution Error: {resp['error']}")
        st.session_state.last_execution_success = False
        return f"Error: {resp['error']}"

    st.session_state.last_execution_success = True
    rows = resp.get("result", {}).get("rows", [])

    st.markdown("### Query Results")
    st.dataframe(rows)

    # Persist to history so it remains after rerun
    st.session_state.chat_history.append(
        {"role": "assistant", "type": "sql_result", "sql": query, "rows": rows}
    )

    return rows


# 4. Streamlit UI Layout
col_title, col_metric = st.columns([4, 1])
with col_title:
    st.title("🎬 Pagila Database AI Assistant")
with col_metric:
    if "sql_collection" in st.session_state:
        st.metric("Cached Prompts", st.session_state.sql_collection.count())

st.markdown("Ask questions about the movie rental database in plain English.")

with st.expander("📂 View Vector Cache Content"):
    if "sql_collection" in st.session_state:
        cache_data = st.session_state.sql_collection.get()
        if cache_data and cache_data.get("ids"):
            # Prepare data for display
            display_rows = []
            for i, doc in enumerate(cache_data["documents"]):
                meta = cache_data["metadatas"][i] if cache_data["metadatas"] else {}
                row = {"Question": doc, "SQL": meta.get("sql", "")}
                display_rows.append(row)
            st.dataframe(display_rows, use_container_width=True)
        else:
            st.info("Vector cache is empty.")

# Display Chat History
for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        if msg.get("type") == "sql_result":
            st.markdown("### Generated SQL")
            st.code(msg["sql"], language="sql")
            st.markdown("### Query Results")
            st.dataframe(msg["rows"])
        else:
            st.markdown(msg["content"])

# Chat Input
placeholder = "e.g., Top 5 customers who rented the most horror movies."
if user_question := st.chat_input(placeholder):
    # 1. Display User Message
    with st.chat_message("user"):
        st.markdown(user_question)
    st.session_state.chat_history.append({"role": "user", "content": user_question})

    # 2. Agent Execution
    with st.chat_message("assistant"):
        message_placeholder = st.empty()

        # Reset execution state
        st.session_state.last_executed_sql = None
        st.session_state.last_execution_success = False

        # --- Step 1: Check Vector Cache ---
        cached_sql = None
        embedding = get_embedding(user_question)

        if embedding:
            try:
                results = st.session_state.sql_collection.query(
                    query_embeddings=[embedding], n_results=1
                )
                # Distance threshold (lower is better). 0.2 is very strict to prevent false positives
                if results["documents"] and results["distances"][0][0] < 0.2:
                    cached_sql = results["metadatas"][0][0]["sql"]
            except Exception:
                pass  # Cache miss or error, proceed to agent

        if cached_sql:
            st.success("⚡ Retrieved from Local Vector Cache (No API Call for SQL Gen)")
            execute_sql(cached_sql)
            final_text = (
                "I found a similar question in the cache and executed the"
                " stored SQL."
            )
            message_placeholder.markdown(final_text)
            st.session_state.chat_history.append(
                {"role": "assistant", "content": final_text}
            )
        else:
            # --- Step 2: Run Agent ---
            st.info("🤖 Agent Generating SQL via Gemini API...")
            with st.spinner("Agent is thinking..."):
                try:
                    # 5. Configure the Agent with Tools
                    tools = [list_tables, get_table_schema, execute_sql]

                    # Load metadata
                    metadata_text = load_metadata()

                    system_instruction = f"""
                    You are a helpful database analyst assistant.
                    Your goal is to answer the user's question by querying the
                    database.

                    Database Metadata:
                    {metadata_text}

                    Follow this strict process:
                    1. Review the Database Metadata to understand the schema.
                    2. Call `get_table_schema` for the specific tables
                       relevant to the question to verify column names.
                    3. Construct a valid PostgreSQL query based on the schema
                       you retrieved.
                       - Always cast dates to 'YYYY-MM-DD' format if
                         comparing strings.
                       - Use ILIKE for case-insensitive text matching.
                    4. Call `execute_sql` to run the query.
                    5. Analyze the results and provide a clear, natural
                       language answer to the user.
                    """

                    model = genai.GenerativeModel(
                        selected_model,
                        tools=tools,
                        system_instruction=system_instruction,
                    )

                    # Start a chat session with automatic function calling enabled
                    chat = model.start_chat(enable_automatic_function_calling=True)

                    # Send message
                    response = chat.send_message(user_question)

                    # Calculate Usage & Cost
                    if response.usage_metadata:
                        in_tokens = response.usage_metadata.prompt_token_count
                        out_tokens = response.usage_metadata.candidates_token_count

                        st.session_state.token_metrics["input"] += in_tokens
                        st.session_state.token_metrics["output"] += out_tokens

                        # Cost calc (USD)
                        prices = PRICING.get(selected_model, {"input": 0, "output": 0})
                        input_cost = (in_tokens / 1_000_000) * prices["input"]
                        output_cost = (out_tokens / 1_000_000) * prices["output"]
                        cost = input_cost + output_cost

                        st.session_state.token_metrics["total_cost"] += cost
                        st.session_state.global_metrics["input"] += in_tokens
                        st.session_state.global_metrics["output"] += out_tokens
                        st.session_state.global_metrics["total_cost"] += cost
                        save_global_stats(st.session_state.global_metrics)

                    # 6. Display Final Answer & Update History
                    final_text = response.text
                    message_placeholder.markdown(final_text)
                    st.session_state.chat_history.append(
                        {"role": "assistant", "content": final_text}
                    )

                    # --- Step 3: Cache Successful SQL ---
                    if (
                        st.session_state.last_executed_sql
                        and st.session_state.last_execution_success
                        and embedding
                    ):
                        st.session_state.sql_collection.add(
                            ids=[hashlib.md5(user_question.encode()).hexdigest()],
                            embeddings=[embedding],
                            metadatas=[
                                {
                                    "sql": st.session_state.last_executed_sql,
                                    "question": user_question,
                                }
                            ],
                            documents=[user_question],
                        )

                    # Force rerun to update sidebar metrics immediately
                    st.rerun()

                except Exception as e:
                    st.error(f"An error occurred: {str(e)}")
