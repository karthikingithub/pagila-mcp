
# Pagila Database AI Assistant

This project is a Streamlit-based chatbot that allows users to query a PostgreSQL database (Pagila schema) using natural language. It leverages Google's Gemini API for SQL generation and the Model Context Protocol (MCP) for secure database execution.

## Features

*   **Natural Language to SQL**: Converts English questions into valid SQL queries.
*   **Agentic Workflow**: The AI autonomously explores the database schema (listing tables, checking columns) before writing queries.
*   **Vector Caching (RAG)**: Uses ChromaDB to cache successful SQL queries locally. If a similar question is asked again, the cached SQL is executed immediately, saving API costs and time.
*   **Model Context Protocol (MCP)**: Uses a dedicated local server (`mcp_pagila_server.py`) to handle database operations, separating the UI from the backend logic.
*   **Cost Tracking**: Monitors token usage and estimates costs for both the current session and global history.
*   **Schema Visualization**: Displays the database schema diagram and metadata within the UI.

## Architecture

1.  **Frontend**: Streamlit (`app.py`) handles user input, chat history, and visualization.
2.  **AI Brain**: Google Gemini (via `google-generativeai`) acts as the reasoning engine.
3.  **Backend**: An MCP Server (`mcp_pagila_server.py`) runs as a subprocess, exposing tools like `list_tables`, `get_table_schema`, and `execute_sql`.
4.  **Database**: PostgreSQL hosting the Pagila sample database.
5.  **Cache**: ChromaDB stores embeddings of questions and their corresponding SQL.

## Prerequisites

*   Python 3.10+
*   PostgreSQL database with the **Pagila** schema installed.
*   Google Gemini API Key.

## Installation

1.  **Clone the repository**:
    ```bash
    git clone <repository-url>
    cd mcp-pagila-server
    ```

2.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

3.  **Configure Environment**:
    Create a `config.env` file in the root directory:
    ```env
    GEMINI_API_KEY=your_google_api_key_here
    PGHOST=localhost
    PGUSER=your_postgres_user
    PGPASSWORD=your_postgres_password
    PGDATABASE=pagila
    LOG_DIR=logs
    ```
    *Note: It is recommended to use a read-only database user for security.*

## Usage

Run the Streamlit application:

```bash
streamlit run app.py
```
### Testing & Inspection + +streamlit_app.py is provided as a lightweight, chat-like interface to test the MCP server directly without the full Gemini Agent loop. It is useful for debugging the MCP server connection and running raw SQL (using a run: prefix) or heuristic-based queries
## Project Structure

*   `app.py`: Main Streamlit application.
*   `mcp_pagila_server.py`: MCP server implementation.
*   `pagila-metadata.txt`: Text-based schema summary for the AI.
*   `requirements.txt`: Python dependencies.
*   `vector_store/`: Directory where ChromaDB persists data (ignored in git).
*   `usage_stats.json`: Local file tracking usage costs (ignored in git).