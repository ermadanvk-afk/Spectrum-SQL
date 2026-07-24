# Architecture Documentation — Text-to-SQL ERP Assistant

**Project:** Text-to-SQL ERP Integration Tool  
**Internship Period:** Summer 2026  
**Architecture Pattern:** Pipeline-Based Query Processing  
**Model Backend:** Google Gemini Flash  
**API Layer:** FastAPI (REST)

---

## 1. System Architecture Overview

The Text-to-SQL ERP Assistant follows a **multi-stage pipeline architecture**. Each user query traverses a sequence of specialized layers — from intent detection and context retrieval to SQL generation, validation, and execution. This design ensures accuracy, security, and low-latency responses while maintaining strict data governance over ERP databases.

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Intent    │───▶│    RAG      │───▶│   Context   │───▶│   SQL Gen   │───▶│  Validator  │
│ Classification│   │  Retrieval  │    │  Assembly   │    │  (Gemini)   │    │   & Exec    │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
                                                                                      │
                                                                                      ▼
                                                                              ┌─────────────┐
                                                                              │   Response  │
                                                                              │  Rendering  │
                                                                              └─────────────┘
```

---

## 2. Pipeline Stages

### 2.1 Intent Classification
The first gate determines whether a user query is **business-relevant** or general conversational text.

- **Mechanism:** Natural Language Inference (NLI) model
- **Principle:** Semantic comparison between a **premise** (the user's question) and a **hypothesis** (business-domain intent). The NLI model classifies the relationship as entailment, contradiction, or neutral, effectively filtering out off-topic queries before they reach the database layer.

### 2.2 RAG Retrieval Layer
This is the most critical stage — it prepares the contextual grounding required for accurate SQL generation.

#### RAG Knowledge Base Setup
The vector database is populated with three distinct knowledge sources, stored in a **single vector store** differentiated by metadata tags for filtered retrieval:

| Source | Content |
|--------|---------|
| **Database Schema** | Table structures, column definitions, data types, primary/foreign key relationships |
| **Business Rules** | Domain constraints, access policies, entity definitions |
| **Golden Queries** | Curated sample SQL queries representing common business patterns |

**Embedding Payload Structure:**
```
schema_name | table_name | column_name | data_type | is_primary_key | is_foreign_key
referenced_schema | referenced_table | referenced_column | Business Entity | purpose
supports | does_not_support | schema_name
```

#### Retrieval Engineering (Iterative Improvements)

| Iteration | Enhancement | Purpose |
|-----------|-------------|---------|
| **v1** | Basic dense embedding + similarity search | Baseline retrieval |
| **v2** | **Hybrid Retrieval** — Dense + Sparse embeddings stored simultaneously; top-k results from both methods are re-ranked using **Reciprocal Rank Fusion (RRF)** | Improves recall by combining semantic and lexical matching |
| **v3** | **Cross-Encoder Reranker** — A dedicated reranker model re-scores retrieved chunks to surface the most relevant tables | Boosts precision by filtering noise from initial retrieval |
| **v4** | **Tuned Table Descriptions** — Business intent injected into table descriptions to guide semantic search toward correct table selection | Aligns embeddings with real-world business semantics |
| **v5** | **Dual-Payload Strategy** — Two separate embedding payloads:  <br>• **RAG Payload**: Includes `supports` / `does_not_support` statements for fine-tuning semantic search relevance  <br>• **LLM Payload**: Includes `purpose` and usage instructions for the AI's SQL generation context | Separates retrieval needs (relevancy) from generation needs (definition/actionability) |

**Retrieval Flow:**
```
User Query ──▶ Retrieve Table Metadata ──▶ Retrieve Business Rules ──▶ Retrieve Golden Queries
                                    │
                                    ▼
                        Hybrid Search (Dense + Sparse + RRF)
                                    │
                                    ▼
                        Cross-Encoder Reranker (Re-scoring)
                                    │
                                    ▼
                        Filtered, Ranked Context Chunks
```

### 2.3 Context Assembly & System Prompt
Retrieved context is assembled into a structured system prompt delivered to Gemini Flash.

- **Format:** XML-structured prompt for easy parsing and deterministic structured output
- **Iterations:** The system prompt underwent **10–15 refinement cycles** to achieve reliable, context-aware SQL generation with consistent schema adherence

### 2.4 SQL Generation (Gemini Flash)
The LLM receives the assembled context and user query, then generates a syntactically correct, schema-aligned SQL query optimized for the target ERP database.

### 2.5 SQL Validator & Execution Engine
Before any query touches the database, it passes through a rigorous multi-layer validation pipeline:

| Check | Method | Purpose |
|-------|--------|---------|
| **Harmful Command Detection** | AST (Abstract Syntax Tree) parsing | Blocks DDL/DML commands: `CREATE`, `DELETE`, `INSERT`, `DROP`, `UPDATE`, `ALTER` |
| **Role-Based Access Control** | Schema-aware table whitelist | Ensures the query only references tables the user's role is authorized to access |
| **Schema Validation** | `NOEXEC` / dry-run parsing | Verifies all referenced tables and columns exist in the actual database schema |
| **Safe Execution** | 45-second query timeout | Prevents runaway/heavy queries from throttling the database |
| **Connection Management** | Connection pooling | Reuses established DB connections instead of re-creating them per request |
| **Result Limiting** | Hard cap of **3,000 rows** | Protects application performance when unfiltered queries are issued |

**Error Handling & Retries:**
- If validation fails, the system grants **2 retry attempts** with the error log fed back to the LLM for self-correction
- If all retries exhaust, a graceful apology message is returned to the user

### 2.6 Response Rendering (FastAPI)
Validated results are returned via **FastAPI REST endpoints** to the React frontend for display.

---

## 3. Analysis Modules Architecture

### 3.1 Auto Analysis
Transforms raw SQL result sets into narrative business insights.

**Pipeline:**
```
SQL Result ──▶ Pandas DataFrame ──▶ Summary Statistics ──▶ LLM (Pandas Code Generation)
                                                              │
                                                              ▼
                                                    Python Code (exec())
                                                              │
                                                              ▼
                                                    Analytical Results ──▶ LLM Storytelling
```

- The LLM generates **Pandas-based analytical queries** (aggregation, grouping, trend analysis) rather than SQL, saving significant token costs
- Code is executed at runtime via Python's `exec()` with **OS-level restrictions** to prevent harmful system access
- Final output is phrased as **storytelling bullet points** for executive readability

**Trade-off:** Token efficiency vs. sandbox risk — mitigated via restricted execution environment.

### 3.2 Visual Analysis
Generates interactive data visualizations from tabular results.

**Pipeline:**
```
SQL Result ──▶ Pandas DataFrame ──▶ LLM (Vega-Lite Spec Generation) ──▶ Vega-Embed (React)
```

- The LLM outputs **Vega-Lite embed specifications** describing the desired chart
- The React frontend renders these specs using the **Vega-Embed** library
- AI-generated insights are appended alongside the visualization for contextual interpretation

---

## 4. Data Flow Summary

```
User Input
    │
    ▼
┌─────────────────┐
│ Intent Check    │ ──▶ Reject if non-business
│ (NLI Model)     │
└─────────────────┘
    │
    ▼
┌─────────────────┐
│ RAG Retrieval   │ ──▶ Hybrid Search + Reranker
│ (Vector DB)     │ ──▶ Table Metadata + Rules + Golden Queries
└─────────────────┘
    │
    ▼
┌─────────────────┐
│ Context Assembly│ ──▶ XML System Prompt
│ + SQL Generation│ ──▶ Gemini Flash
└─────────────────┘
    │
    ▼
┌─────────────────┐
│ SQL Validator   │ ──▶ AST Parse → Role Check → Schema Check
│ + Execution     │ ──▶ 45s Timeout → 3000 Row Cap → Connection Pool
└─────────────────┘
    │
    ▼
┌─────────────────┐
│ Response        │ ──▶ FastAPI → React Frontend
│ Rendering       │ ──▶ Raw Table / Auto Analysis / Visual Analysis
└─────────────────┘
```

---

## 5. Key Architectural Decisions

| Decision | Rationale |
|----------|-----------|
| **Pipeline over End-to-End** | Modular validation at each stage prevents cascading errors and enables fine-grained security |
| **Hybrid RAG + Reranker** | Maximizes both recall (hybrid) and precision (reranker) for schema-heavy domains |
| **Dual Payload Embeddings** | Separates retrieval semantics from generation context, improving both accuracy and token efficiency |
| **Pandas-based Auto Analysis** | Drastically reduces LLM token consumption vs. passing full tables for narrative generation |
| **Vega-Lite for Visualization** | Declarative, lightweight spec format ideal for LLM generation and frontend rendering |
| **FastAPI Backend** | High-performance async REST API with native Python ecosystem integration |

---

*Document Version: 1.0 | Last Updated: July 2026*
