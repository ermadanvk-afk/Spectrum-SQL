import os
import time
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from contextlib import asynccontextmanager
import asyncio
from transformers import pipeline

from sql_gen import generate_sql
from validator import validate_and_fix_sql
from execute import execute_query
from expense import calculate_cost
from embedder import get_m3_model
import pandas as pd
from analytics.analyzer import generate_analytical_summary

from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(env_path)
conn_str = os.getenv("DB_CONNECTION_STRING")

class QueryRequest(BaseModel):
    query: str
    history: list[dict] = []

class AnalyzeDataRequest(BaseModel):
    query: str
    data: list[dict]

nli_classifier = None

def get_nli_classifier():
    global nli_classifier
    if nli_classifier is None:
        print("Loading NLI model for intent classification...")
        nli_classifier = pipeline(
            "zero-shot-classification",
            model="cross-encoder/nli-deberta-v3-small"
        )
    return nli_classifier

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Warming up BGE-M3 model on startup...")
    get_m3_model()
    print("Warming up NLI model on startup...")
    get_nli_classifier()
    yield
    print("Shutting down...")

app = FastAPI(title="Text to SQL API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def run_pipeline(request_model: QueryRequest):
    # Step 0: Intent Classification (NLI)
    classifier = get_nli_classifier()
    valid_intent = "A question about Enterprise ERP database data, procurement, purchase orders, items, or suppliers, analytical queries for procurement data, material management, inventory "
    fallback_intent = "A general conversational question, small talk, weather, stock market, or unrelated topic."
    candidate_labels = [valid_intent, fallback_intent]
    
    # Run the classification
    nli_result = classifier(request_model.query, candidate_labels)
    top_intent = nli_result['labels'][0]
    
    valid_index = nli_result['labels'].index(valid_intent)
    valid_score = nli_result['scores'][valid_index]
    
    print(f"\n[NLI INTENT] Query: '{request_model.query}'")
    print(f"[NLI INTENT] Predicted Intent: {top_intent} (Scores: {nli_result['scores']})")
    
    if top_intent != valid_intent or valid_score < 0.5:
        # Fallback for small talk or unrelated questions
        return {
            "status": "success",
            "explanation": "I apologize, I am an ERP procurement analytics assistant and am not intended for this task.",
            "sql": None,
            "original_sql": None,
            "data": [],
            "cost": None
        }

    # Step 1: Generate SQL
    sql_raw, response_obj, chat, full_prompt, explanation = await generate_sql(
        request_model.query, 
        return_response=True,
        history=request_model.history
    )
    
    usage = response_obj.usage_metadata
    in_tok = getattr(usage, "prompt_token_count", 0)
    out_tok = getattr(usage, "candidates_token_count", 0)
    
    # Step 2: Validate SQL
    is_valid, final_sql, retry_in, retry_out = await validate_and_fix_sql(
        sql_raw, 
        request_model.query, 
        chat=chat
    )
    in_tok += retry_in
    out_tok += retry_out
    
    if not is_valid:
        raise HTTPException(status_code=400, detail="Query validation failed. Unable to safely generate SQL.")
        
    # Step 3: Execute SQL
    if not conn_str or conn_str == "your_sql_server_connection_string":
        raise HTTPException(status_code=500, detail="Database connection string not configured.")
        
    columns, rows = execute_query(final_sql, connection_string=conn_str)
    
    # Calculate cost
    cost_info = calculate_cost(in_tok, out_tok)
    
    return {
        "status": "success",
        "explanation": explanation,
        "sql": final_sql,
        "original_sql": sql_raw if sql_raw != final_sql else None,
        "data": rows,
        "cost": cost_info
    }

@app.post("/api/ask")
async def ask_question(request_model: QueryRequest, request: Request):
    try:
        # Wrap the whole pipeline in an asyncio task
        pipeline_task = asyncio.create_task(run_pipeline(request_model))
        
        # Poll for client disconnect
        while not pipeline_task.done():
            if await request.is_disconnected():
                pipeline_task.cancel()
                print("\n[NVIDIA PIPELINE] 🛑 Request aborted by client disconnect!")
                # Just return an empty response, the client already hung up
                return {}
            await asyncio.sleep(0.5)
            
        return await pipeline_task
        
    except asyncio.CancelledError:
        print(f"\n[NVIDIA PIPELINE] 🛑 Request aborted by client!")
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/analyze")
async def analyze_data(request_model: AnalyzeDataRequest):
    if not request_model.data:
        return {"status": "error", "type": "error", "content": "No data provided for analysis."}
        
    df = pd.DataFrame(request_model.data)
    result = await generate_analytical_summary(df, request_model.query)
    return result

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host= "localhost", port=8000, reload=True)
