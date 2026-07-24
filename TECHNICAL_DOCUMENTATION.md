# Spectrum SQL — Technical Documentation

> **Audience:** New contributors, backend developers, and ML engineers joining this project.
> **Last Updated:** July 2026
> **Stack:** Python 3.11+, FastAPI, SQLite, Qdrant, Gemini Flash, BGE-M3, Nemotron, React/Vite (frontend)

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture Diagram](#2-architecture-diagram)
3. [Repository Structure](#3-repository-structure)
4. [Module-by-Module Reference](#4-module-by-module-reference)
5. [Configuration Files](#5-configuration-files)
6. [The Full Request Lifecycle](#6-the-full-request-lifecycle)
7. [Authentication and Authorization Model](#7-authentication-and-authorization-model)
8. [RAG Pipeline Deep Dive](#8-rag-pipeline-deep-dive)
9. [Setting Up From Scratch](#9-setting-up-from-scratch)
10. [Key Dos and Donts](#10-key-dos-and-donts)
11. [Common Pitfalls and Debugging Guide](#11-common-pitfalls-and-debugging-guide)
12. [API Reference](#12-api-reference)

---

## 1. Project Overview

**Spectrum SQL** is a **Text-to-SQL** application built for an Enterprise ERP (procurement domain). A user types a natural language question in the chat UI (React frontend), and the system:

1. **Classifies intent** — rejects greetings/off-topic queries via a local NLI model.
2. **Retrieves schema context** (RAG) — finds the most relevant DB tables, business rules, and sample queries from a local Qdrant vector store.
3. **Generates SQL** — sends context + question to Google Gemini Flash via the OpenAI-compatible API.
4. **Validates and repairs SQL** — uses SQLFluff (syntax), SQLGlot (semantics/RBAC), and an actual `SET FMTONLY ON` dry-run against the target SQL Server.
5. **Executes the query** — runs the validated SQL and streams back results (max 3,000 rows).
6. **Logs everything** — every pipeline step is written to a `system_logs` SQLite table for admin traceability.

---

## 2. Architecture Diagram

```
User (Browser/React)
        |  POST /api/ask
        v
+----------------------------------------------------------+
|                    main.py (FastAPI)                     |
|  Auth --> Session Management --> run_pipeline()          |
+-------------------------+--------------------------------+
                          |
          +---------------v---------------+
          |   Step 0: NLI Intent          |  (local DeBERTa model)
          |   Intent classification        |
          +---------------+---------------+
                          | valid intent
          +---------------v---------------+
          |   Step 1: sql_gen.py          |
          |   RAG Context + Gemini LLM    |---> Qdrant Vector Store
          +---------------+---------------+       (retriever.py)
                          | raw SQL
          +---------------v---------------+
          |   Step 2: validator.py        |
          |   SQLFluff + SQLGlot +        |
          |   RBAC + DB Dry-Run           |
          +---------------+---------------+
                          | validated SQL
          +---------------v---------------+
          |   Step 3: execute.py          |---> Target SQL Server (pyodbc)
          |   execute_query()             |
          +---------------+---------------+
                          | columns + rows
          +---------------v---------------+
          |   Response assembly           |
          |   + logger.py (SQLite)        |
          +---------------+---------------+
                          | JSON response
                     React UI
```

---

## 3. Repository Structure

```
approch 4/
+-- nvidia/                   # All Python backend code lives here
|   +-- main.py               # FastAPI app, routes, pipeline orchestrator
|   +-- sql_gen.py            # SQL generation via Gemini
|   +-- validator.py          # SQL validation, RBAC, dry-run
|   +-- retriever.py          # Qdrant RAG retrieval + reranking
|   +-- embedder.py           # BGE-M3 embeddings + Nemotron reranker
|   +-- vector_store.py       # Qdrant ingestion pipeline (run once)
|   +-- schema_chunker.py     # Converts Excel schema to Qdrant chunks
|   +-- execute.py            # Runs validated SQL on target SQL Server
|   +-- connect.py            # SQLAlchemy engine pool for SQL Server
|   +-- database.py           # SQLite ORM models (sessions, messages, users)
|   +-- auth.py               # JWT creation, verification, bcrypt hashing
|   +-- logger.py             # Synchronous structured logger -> SQLite
|   +-- expense.py            # Token cost calculator (INR + USD)
|   +-- load_df.py            # Loads Excel schema sheets into DataFrames
|   +-- systemprompt.txt      # LLM system instruction (T-SQL rules)
|   +-- intent_valid.txt      # NLI label: valid business query description
|   +-- intent_fallback.txt   # NLI label: off-topic query description
|   +-- boosting.json         # Keyword -> table boost scores
|   +-- server_config.json    # Uvicorn config
|   +-- .env                  # SECRETS - never commit this!
|
+-- spectrum_SQL/             # React + Vite frontend
|   +-- src/
|
+-- new_qdrant_db/            # Qdrant local vector database (auto-generated)
+-- spectrum.db               # SQLite database (sessions, messages, logs)
+-- requirements.txt
+-- roles_config.json         # Role -> table access mapping (for setup)
```

---

## 4. Module-by-Module Reference

### 4.1 main.py — FastAPI Server and Orchestrator

**Purpose:** Entry point. Manages HTTP routing, session lifecycle, authentication guards, and orchestrates `run_pipeline()`.

#### Startup (lifespan)

When the server starts, it:
1. Runs `init_db()` — creates all SQLite tables if they don't exist.
2. Loads BGE-M3 (`get_m3_model()`) into GPU/CPU memory.
3. Loads the NLI DeBERTa classifier (`get_nli_classifier()`) into memory.

> **Why preload?** These models take 5-30 seconds to load. Doing it at startup prevents cold-start latency on the first user request.

#### Key Function: run_pipeline()

```python
async def run_pipeline(query, history, log_id, allowed_access, connection_string) -> dict
```

The core 3-step chain:

| Step | Module Called | What It Does |
|------|--------------|--------------|
| 0 | NLI classifier | Rejects off-topic queries before spending LLM tokens |
| 1 | `sql_gen.generate_sql()` | Generates raw SQL with RAG context |
| 2 | `validator.validate_and_fix_sql()` | Validates, RBAC-checks, dry-runs SQL |
| 3 | `execute.execute_query()` | Executes on target SQL Server |

#### Session History (Sliding Window)

Only the last **3 successful Q->SQL pairs** are passed to the LLM as conversation history. This keeps prompts short while preserving follow-up context.

```python
history = successfulPairs[-3:]  # Sliding window of last 3 turns
```

#### Client Disconnect Handling

The pipeline runs as an `asyncio.Task`. The server polls `request.is_disconnected()` every 500ms and cancels the task if the user navigates away — preventing wasted LLM calls.

---

### 4.2 sql_gen.py — LLM SQL Generator

**Purpose:** Assembles a RAG-enriched prompt and calls Gemini to generate SQL.

#### LLM Client Setup

```python
client = AsyncOpenAI(
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    api_key=_api_key,
    timeout=120.0
)
```

The standard OpenAI SDK is reused against Google's OpenAI-compatible endpoint. You can swap to any OpenAI-compatible provider by changing just the `base_url`.

#### Prompt Assembly Order

The prompt is built in this strict order (matches `systemprompt.txt` expectations):

1. `# Business Rules` — domain rules for the relevant tables
2. `# Database Schema` — table/column definitions
3. `# Golden Queries` — few-shot SQL examples
4. `# Conversation History (Last 3 Interactions)` — prior Q&A pairs
5. `# Target Question` — the actual user query

#### Response Parsing

The LLM is instructed to output in this format:

```
<explanation>One sentence.</explanation>

[sql block with SELECT statement]
```

The code uses two regex patterns:
- SQL: `` r"```sql\n?(.*?)\n?```" ``
- Explanation: `r"<explanation>(.*?)</explanation>"`

#### OpenAIChatWrapper

A stateful class that keeps the message list between the initial generation and any validation retries. When the validator asks for a fix, it appends the error message to the *same chat history* rather than starting fresh — preserving context.

---

### 4.3 validator.py — SQL Validator and Fixer

**Purpose:** Multi-layer SQL safety net that catches syntax errors, security violations, and schema mismatches before execution.

#### Validation Pipeline (per attempt)

| Layer | Tool | What It Catches |
|-------|------|-----------------|
| L1 | SQLFluff (T-SQL dialect) | Syntax errors |
| L2 | SQLGlot AST parse | Non-SELECT statements (INSERT/DROP/etc.) |
| L3 | SQLGlot Star check | `SELECT *` usage |
| L4 | RBAC check | Tables/columns the user's role cannot access |
| L5 | `SET FMTONLY ON` dry-run | Nonexistent columns, wrong joins |

#### Retry Logic

Up to **2 retries** on failure:

```python
async def validate_and_fix_sql(..., max_retries: int = 2) -> tuple[bool, str, int, int]:
```

On each failure, a `retry_prompt` is sent back through the `OpenAIChatWrapper` (the same conversation). The LLM sees the error message and re-generates corrected SQL.

#### AUTH_ERROR vs Hard Failure

- `AUTH_ERROR:` prefix -> returned to the user as a friendly permission denial (not a crash).
- Other errors -> retried, then returned as `UNABLE_TO_GENERATE` after exhausting retries.

#### sanitize_sql()

Normalizes Unicode math symbols (`>=` and `<=`) that some LLMs occasionally output using special Unicode characters.

---

### 4.4 retriever.py — RAG Retriever

**Purpose:** Finds the most relevant schema chunks, business rules, and sample queries from Qdrant for a given user query.

#### Retrieval Strategy: Hybrid Fusion (Dense + Sparse RRF)

For each query, two parallel searches run inside Qdrant:
- **Dense** (BGE-M3 1024-dim vectors) — semantic similarity
- **Sparse** (BM25-style lexical weights) — keyword matching

Results are merged using **Reciprocal Rank Fusion (RRF)** — a rank-based fusion that is robust even when the two ranking sources disagree.

#### Two-Stage Table Retrieval

Tables go through an extra reranking step:
1. Fetch top-16 candidates via RRF.
2. Score each with the **Nemotron reranker** (via OpenRouter API).
3. Apply keyword boost scores from `boosting.json`.
4. Return top-8 final tables.

#### Keyword Boosting (boosting.json)

Some tables are hard to find semantically. `boosting.json` maps keywords to tables with a boost score that is added to the reranker score.

```json
{
  "expense": { "tables": ["dbo.vwExpenseVoucher"], "boost_score": 0.5 },
  "*": { "tables": ["dbo.CompanyMaster"], "boost_score": 0.3 }
}
```

The `"*"` key means "always include these tables regardless of query."

#### Business Rules Fetching Strategy

- **Table-specific rules**: All rules for the retrieved tables are fetched via a metadata filter scroll (no vector search — avoids top-k cutoffs).
- **General rules**: Top-K semantic search for rules in the `"general"` category.

---

### 4.5 embedder.py — Embedding and Reranking

**Purpose:** Produces hybrid embeddings for both ingestion and query-time retrieval.

#### BGE-M3 Model

```python
model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=True)
```

- Produces **dense vectors** (1024-dim) for semantic search.
- Produces **sparse lexical weights** (BM25-style) for keyword search.
- ColBERT vectors are disabled (`return_colbert_vecs=False`) to save GPU memory.
- Loaded once as a global singleton (`_M3_MODEL`).

#### Nemotron Reranker

Model: `nvidia/llama-nemotron-rerank-vl-1b-v2:free` via OpenRouter

A cross-encoder reranker that scores each (query, table_schema) pair more accurately than bi-encoder retrieval. Falls back to `[0.0, ...]` if the API times out — the pipeline continues degraded rather than crashing.

---

### 4.6 vector_store.py — Qdrant Ingestion

**Purpose:** One-time setup script to build the vector database from the Excel schema sheet.

**Run this whenever the schema changes:**

```bash
python nvidia/vector_store.py
```

#### Collection Schema

```
Collection: "schema_chunks"
  vectors:
    dense:  1024-dim, Cosine distance
    sparse: SparseVectorParams (in-memory index)
  payload fields:
    chunk_type:  "table" | "business_rule" | "sample_query"
    text:        embedding text (rich, with metadata)
    llm_text:    clean schema string (sent to LLM, no noise)
    sql:         (sample_query only) the golden SQL
    category:    (business_rule only) table name or "general"
```

> **Important:** `vector_store.py` **wipes and recreates** the entire Qdrant folder on every run. This is intentional to avoid orphaned stale chunks when tables are renamed or deleted.

---

### 4.7 schema_chunker.py — Schema Preprocessing

**Purpose:** Converts raw Excel rows into structured Qdrant-ready chunks.

#### Two Text Representations per Table Chunk

| Field | Used For | Contains |
|-------|----------|----------|
| `embedding_text` | Qdrant embedding + query-time matching | Business Entity, purpose, supports, does-not-support, column names (no data types) |
| `llm_text` | Sent inside the LLM prompt | Column names with data types, FK relationships, purpose |

> **Why two versions?** The embedding text is enriched with semantic metadata to improve retrieval. The LLM text is clean and precise to avoid confusing the model with irrelevant fields. Data types are noise for embeddings but critical for SQL generation.

#### Three Chunk Types

| Builder Function | Input Sheet | Output Chunk Type |
|-----------------|-------------|-------------------|
| `build_table_chunks()` | `views` sheet | `"table"` |
| `build_business_rule_chunks()` | `BR` sheet | `"business_rule"` |
| `build_sample_query_chunks()` | `Sheet8` | `"sample_query"` |

---

### 4.8 execute.py — SQL Execution

**Purpose:** Runs validated SQL against the target SQL Server and returns column names + rows.

```python
def execute_query(sql, connection_string, timeout_seconds=45, log_id=None) -> tuple[list[str], list[dict]]
```

- **Row cap:** `result.fetchmany(3000)` — hard-coded to prevent memory crashes on queries that accidentally return millions of rows.
- **Error handling:** All SQL Server errors are caught and re-raised as a user-friendly `RuntimeError` message rather than exposing raw ODBC error strings to the frontend.

---

### 4.9 connect.py — DB Connection Pool

**Purpose:** Manages a process-level SQLAlchemy engine pool for the target SQL Server(s).

```python
_engines = {}  # connection_string -> Engine (singleton per connection string)
```

Multiple databases (from `DBMaster`) can be connected simultaneously. Each connection string maps to exactly one pooled engine with:

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `pool_size` | 5 | Persistent connections |
| `max_overflow` | 10 | Max extra burst connections |
| `pool_pre_ping` | True | Validates connections before use |
| `pool_recycle` | 3600 | Recreates connections every hour |

---

### 4.10 database.py — Internal ORM Models

**Purpose:** Defines all SQLite ORM models for the application's own state (not the customer's SQL Server).

#### Data Model Overview

```
User -----(many-to-many)----- Role
  |                              |
  | has                          | defines
  v                              v
UserDatabaseAccess        RoleTableAccess
  |                        (table + restricted columns)
  | points to
  v
DBMaster (connection strings)

Session --(1:many)--> Message
                          |
                          +-- referenced by --> SystemLog
```

#### Key Models

| Model | Table | Purpose |
|-------|-------|---------|
| `User` | `users` | User accounts; `user_type=1` = Admin, `2` = Regular |
| `Session` | `sessions` | Chat session (UUID) with a user and display title |
| `Message` | `messages` | Every chat turn — stores SQL, data (JSON), explanation, cost |
| `Role` | `roles` | Named role (e.g., "Finance", "Procurement") |
| `RoleTableAccess` | `role_table_access` | Which tables+columns a role can query |
| `DBMaster` | `db_master` | Target database registry (name + connection string) |
| `RefreshToken` | `refresh_tokens` | Issued refresh tokens with revocation support |

---

### 4.11 auth.py — JWT Authentication

**Purpose:** Password hashing and JWT lifecycle management.

#### Token Strategy

| Token | Expiry | Storage | Purpose |
|-------|--------|---------|---------|
| Access Token | 180 min | `httponly` cookie | API auth on every request |
| Refresh Token | 360 min | `httponly` cookie + DB | Obtain new access tokens |

**Rotation:** On every `/api/auth/refresh` call, the old refresh token is marked `revoked=True` in the DB and a new one is issued (refresh token rotation).

**Cookie flags:** `httponly=True, samesite="lax", secure=False`

> WARNING: For production, set `secure=True` to enforce HTTPS-only cookies.

---

### 4.12 logger.py — Structured Logging

**Purpose:** Provides a synchronous logging layer that writes to the `system_logs` SQLite table.

> **Why synchronous?** The logger is called from both async (FastAPI) and sync contexts (validator). Using a sync SQLAlchemy engine avoids async complexity and event-loop conflicts.

#### Log Lifecycle for One Request

```
create_log_sync()          -> Creates row with QUERY_START
update_log_sync_by_id()    -> Updated at each pipeline step
log_error_sync()           -> Appends error details on failure
update_log_sync_by_id()    -> Relinks log to assistant message_id
```

#### Key Fields in system_logs

| Field | Description |
|-------|-------------|
| `user_query` | Original user question |
| `tables_retrieved` | JSON list of tables before reranking |
| `tables_after_reranking` | JSON list after Nemotron reranking |
| `business_rules` | Rules injected into the prompt |
| `sample_queries` | Few-shot examples injected |
| `generated_sql` | The final SQL that passed validation |
| `validation_status` | `SUCCESS` or `FAILED` |
| `execution_status` | `SUCCESS` or `FAILED` |
| `is_useful` / `user_comment` | User feedback (thumbs up/down + comment) |

---

### 4.13 expense.py — Token Cost Tracker

**Purpose:** Calculates Gemini API token costs in USD and INR.

```
Input cost:  $0.25 / 1M tokens
Output cost: $1.50 / 1M tokens
Exchange:    1 USD = 95 INR (hardcoded — update if needed)
```

The cost is **accumulated** across pipeline stages (initial generation + any validation retries) and stored in `messages.cost` as JSON.

---

## 5. Configuration Files

### .env (in nvidia/)

```
GEMINI_API_KEY=your_gemini_key_here
OPENROUTER_API_KEY=your_openrouter_key_here
DB_CONNECTION_STRING=Driver={ODBC Driver 17 for SQL Server};Server=...;Database=...;UID=...;PWD=...
JWT_SECRET_KEY=a_random_long_secret_string
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000
```

### boosting.json

Maps keywords (lemmatized) to tables that should get a score boost during retrieval.

Format: `{ "keyword": { "tables": ["schema.table"], "boost_score": float } }`

Use `"*"` as key to always-include tables regardless of query content.

### intent_valid.txt / intent_fallback.txt

These plain-text files define the **NLI candidate labels** for query classification.
Edit these to tune what the system accepts as valid business queries.
The threshold for acceptance is `valid_score >= 0.5`.

### systemprompt.txt

The LLM's system instruction. Controls:
- SQL dialect rules (T-SQL, no `LIMIT`, use `SELECT TOP N`)
- Mandatory reasoning steps (business intent -> rule selection -> SQL)
- Strict output format (`<explanation>` tags + sql code block)
- Fallback for unanswerable queries: `SELECT NULL AS Message WHERE 1 = 0;`

---

## 6. The Full Request Lifecycle

```
POST /api/ask  { query, session_id?, db_id? }
|
+-- [Auth] get_current_user() -- validates JWT cookie
+-- [Session] create or fetch session, verify ownership
+-- [History] load last 3 successful Q->SQL pairs (defer heavy JSON columns)
+-- [Message Limit] reject if > 10 user messages in session
+-- [RBAC Load] fetch allowed tables + restricted columns for user's roles
+-- [DB Resolution] determine target connection string (db_id or user's default)
|
+-- [Log] create_log_sync() -> log_id
|
+-- asyncio.create_task(run_pipeline(...))
    |
    +-- Step 0: NLI classify -> reject if off-topic
    +-- Step 1: sql_gen.generate_sql()
    |   +-- retriever.fetch_tables()
    |   |   +-- embed_m3(query) -> dense + sparse vectors
    |   |   +-- Qdrant hybrid RRF search (top-16)
    |   |   +-- get_nemotron_reranker_scores()
    |   |   +-- keyword boost -> top-8 tables
    |   +-- retriever.fetch_business_rules() (all table-specific + top-4 general)
    |   +-- retriever.fetch_sample_queries() (top-3)
    |   +-- Assemble prompt (rules + schema + examples + history + question)
    |   +-- Gemini Flash API -> extract SQL + explanation
    |
    +-- Step 2: validator.validate_and_fix_sql() [up to 3 attempts]
    |   +-- sanitize_sql() (Unicode fix)
    |   +-- SQLFluff parse (T-SQL syntax)
    |   +-- SQLGlot AST (SELECT-only guard, no SELECT *)
    |   +-- RBAC table and column check
    |   +-- SET FMTONLY ON dry-run
    |   +-- on failure: retry via OpenAIChatWrapper with error message
    |
    +-- Step 3: execute.execute_query() -> columns, rows (max 3000)

+-- Poll is_disconnected() every 500ms -> cancel task if client left
+-- Save assistant Message to DB (sql, data, explanation, cost, db_id)
+-- update_log_sync_by_id() -- link log to message_id
+-- Return JSON response
```

---

## 7. Authentication and Authorization Model

### User Types

| `user_type` | Label | Privileges |
|-------------|-------|-----------|
| `1` | Admin | All DBs, all tables, view system logs, manage users |
| `2` | Regular | Only assigned DBs and tables per role |

### RBAC Flow

1. User's roles are loaded with `selectinload`.
2. `RoleTableAccess` rows are queried for all role IDs.
3. Duplicates are deduplicated by table name (first role's restriction wins).
4. The `allowed_access` list is passed to `validate_and_fix_sql()`.
5. Validator checks every table and column in the AST against this list.

### First User Bootstrap

The **first registered user** can register without being logged in (no admin exists yet). All subsequent registrations require an active admin JWT.

---

## 8. RAG Pipeline Deep Dive

### Why Three Chunk Types?

| Chunk Type | Semantic Purpose |
|------------|-----------------|
| `table` | Answers "which table do I need?" |
| `business_rule` | Answers "how do I filter/compute this correctly?" |
| `sample_query` | Provides few-shot SQL examples (reduces hallucination) |

### Dual-Text Architecture for Table Chunks

```
embedding_text (used for vector search)
+-- Business Entity    <- human-readable domain label
+-- purpose            <- what data lives here
+-- supports           <- use cases this table covers
+-- does not support   <- explicit exclusions (reduces false positives)
+-- column names       <- without data types (cleaner for embedding)

llm_text (injected into the LLM prompt)
+-- table_name + schema_name
+-- purpose
+-- columns with data types   <- LLM needs types to write correct SQL
+-- FK relationships
```

- Embedding text maximizes **recall** (broad semantic matching).
- LLM text maximizes **precision** (exact schema facts the model needs).
- Data types are noise for embeddings but critical for SQL generation.

---

## 9. Setting Up From Scratch

### Prerequisites

- Python 3.11+
- Node.js 18+
- ODBC Driver 17 for SQL Server
- NVIDIA GPU recommended (for BGE-M3 inference)

### Backend Setup

```bash
# 1. Create virtualenv
python -m venv myenv
myenv\Scripts\activate  # Windows
source myenv/bin/activate  # Linux/Mac

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure secrets
# Copy and fill in your keys in nvidia/.env

# 4. Build the vector database (run once, or whenever schema changes)
cd nvidia
python vector_store.py

# 5. Start the backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend Setup

```bash
cd spectrum_SQL
npm install
npm run dev       # Dev server on http://localhost:5173
```

### First-Time User Registration

```bash
# Register the first admin (no auth needed for the very first user)
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "SecurePass123", "user_type": 1}'
```

---

## 10. Key Dos and Donts

### DO

- **DO** update `systemprompt.txt` when SQL dialect rules change — it is the single source of truth for LLM behavior.
- **DO** run `vector_store.py` every time the schema Excel is updated — the Qdrant DB will be stale otherwise.
- **DO** use `update_log_sync_by_id(log_id=...)` rather than `update_log_sync(message_id=...)` inside the pipeline — `log_id` is the direct PK and avoids ambiguous lookups.
- **DO** use `asyncio.to_thread()` when calling synchronous logger functions from async context — prevents blocking the event loop.
- **DO** keep `intent_valid.txt` and `intent_fallback.txt` up to date — they are the NLI classifier's labels and must be descriptive.
- **DO** use the `defer()` SQLAlchemy option when loading messages for history — the `data` and `cost` JSON columns are large and not needed for history.
- **DO** check `AUTH_ERROR:` prefix in validator return values — they need special handling in `run_pipeline()` to return a 200 with an error message (not a 400 crash).
- **DO** set `secure=True` on cookies before deploying to production HTTPS.
- **DO** add new tables to `boosting.json` if they are frequently missed by semantic search.

### DON'T

- **DON'T** commit `.env` to git — it contains API keys and the JWT secret.
- **DON'T** call `store_chunks_to_vector_db()` while the FastAPI server is running — it wipes and recreates the Qdrant folder, causing retrieval failures mid-request.
- **DON'T** use `SELECT *` in any SQL — the validator enforces this and will reject and retry the query.
- **DON'T** add non-SELECT statements (INSERT, UPDATE, DELETE, DROP) — the AST check will hard-block them with `UNSAFE_QUERY_DETECTED`.
- **DON'T** change the Qdrant collection schema (vector sizes, field names) without re-running `vector_store.py` — mismatched schemas will cause silent retrieval failures.
- **DON'T** import async modules at module-level inside `logger.py` — it uses a synchronous SQLAlchemy engine by design to avoid event-loop conflicts.
- **DON'T** increase `fetchmany(3000)` without careful memory profiling — large result sets from old ERP databases can exhaust server RAM.
- **DON'T** hardcode connection strings anywhere — always read from `.env` via `os.getenv()`.
- **DON'T** return raw database error messages to the user — wrap them in friendly RuntimeError messages (see `execute.py`).
- **DON'T** skip `SET FMTONLY OFF` in the finally block — leaving FMTONLY on would cause all subsequent queries on that connection to return no data.
- **DON'T** use `LIMIT` in SQL — it is MySQL syntax and will cause SQL Server errors. Use `SELECT TOP N` instead.
- **DON'T** pass the full message history to the LLM — use only the last 3 successful pairs to keep prompt length under control.

---

## 11. Common Pitfalls and Debugging Guide

### "Query validation failed" errors

1. Check `validation_error_log.txt` in the project root — it captures the last raw exception from the validator.
2. Look at `system_logs` in the SQLite DB for `VALIDATION_RETRY` events.
3. Most common causes: column name mismatch, wrong table alias, unsupported T-SQL syntax.

### Empty retrieval results (wrong tables returned)

1. Run `retriever.py` directly from the CLI — it has an interactive test mode.
2. Check Qdrant collection status with: `python -c "from retriever import get_qdrant_client; c=get_qdrant_client(); print(c.get_collection('schema_chunks'))"`
3. Add keywords to `boosting.json` if semantic search consistently misses a table.
4. Check if `intent_valid.txt` is too narrow — it might be rejecting valid queries.

### NLI Classifier rejects valid business queries

- Edit `intent_valid.txt` to broaden the description.
- The threshold is `valid_score < 0.5` — lower this constant in `main.py` if the classifier is too strict.

### BGE-M3 loads slowly or runs out of memory

- The model uses `use_fp16=True` — requires a GPU that supports FP16.
- On CPU-only machines, it will fall back to CPU (very slow, ~5-10s per query).
- The model is a singleton; it only loads once per process startup.

### JWT 401 Unauthorized errors

- Check that `JWT_SECRET_KEY` in `.env` is set and matches across server restarts.
- Access tokens expire after 180 minutes. The frontend should call `/api/auth/refresh` automatically.
- Inspect the cookie in browser DevTools — ensure `access_token` cookie is present.

### Cost accumulation drift

- The `cost` field in `messages` accumulates across analysis calls (`/api/analyze`, `/api/analyze_v2`).
- The initial SQL pipeline cost is set on first save; subsequent analysis calls `PUT /api/messages/{id}` to add to it.

---

## 12. API Reference

### Authentication

| Method | Endpoint | Auth Required | Description |
|--------|----------|---------------|-------------|
| POST | `/api/auth/register` | Admin only (after first user) | Create a new user |
| POST | `/api/auth/login` | None | Login, sets httponly cookies |
| POST | `/api/auth/refresh` | Refresh cookie | Rotate tokens |
| POST | `/api/auth/logout` | None | Revoke tokens, clear cookies |

### Core Query

| Method | Endpoint | Auth Required | Description |
|--------|----------|---------------|-------------|
| POST | `/api/ask` | Yes | Main Text-to-SQL endpoint |
| POST | `/api/analyze` | Yes | Generate AI text analysis of result data |
| POST | `/api/analyze_v2` | Yes | Generate chart/visual spec for result data |

### Sessions and Messages

| Method | Endpoint | Auth Required | Description |
|--------|----------|---------------|-------------|
| GET | `/api/sessions` | Yes | List user's sessions (last 50) |
| POST | `/api/sessions` | Yes | Create a new empty session |
| DELETE | `/api/sessions/{id}` | Yes | Delete session and all its messages |
| GET | `/api/sessions/{id}/messages` | Yes | Get all messages with feedback |
| PUT | `/api/messages/{id}` | Yes | Update analysis/visual_spec/cost |
| POST | `/api/messages/{id}/feedback` | Yes | Submit thumbs up/down + comment |

### Admin Only

| Method | Endpoint | Auth Required | Description |
|--------|----------|---------------|-------------|
| GET | `/api/logs` | Admin only | Paginated system logs with date filters |
| GET | `/api/users` | Admin only | List all users |
| PUT | `/api/users/{id}` | Admin only | Update user (roles, db access, active) |
| DELETE | `/api/users/{id}` | Admin only | Delete user |

### Request Body: /api/ask

```json
{
  "query": "Show me top 10 vendors by spend this year",
  "session_id": "uuid-string-or-null",
  "db_id": 1
}
```

### Response Body: /api/ask

```json
{
  "status": "success",
  "explanation": "Retrieves top 10 vendors ranked by total PO spend in the current year.",
  "sql": "SELECT TOP 10 VendorName, SUM(POAmount) AS TotalSpend ...",
  "original_sql": null,
  "data": [{"VendorName": "ABC Corp", "TotalSpend": 1500000.0}],
  "cost": {"input_tokens": 2100, "output_tokens": 180, "cost_inr": 0.000234},
  "message_id": 42,
  "session_id": "abc-def-...",
  "db_id": 1,
  "log_id": 17
}
```

> If `original_sql` is not `null`, the validator modified the LLM's raw output before execution.

---

*This document covers the `nvidia/` backend in full. For frontend documentation, refer to `spectrum_SQL/README.md`.*
