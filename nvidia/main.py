import os
import time
import traceback
from fastapi import FastAPI, HTTPException, Request,Depends
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
from analytics.analyzer_v2 import generate_visual_summary

from dotenv import load_dotenv
from sqlalchemy.future import select
from sqlalchemy import delete
import json
import uuid

from database import init_db, get_db, Session, Message,User
from auth import get_password_hash, create_access_token, verify_password,decode_access_token
from fastapi.security import OAuth2PasswordBearer

env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(env_path)
conn_str = os.getenv("DB_CONNECTION_STRING")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
async def get_current_user(token: str = Depends(oauth2_scheme),db:AsyncSession=Depends(get_db)) -> User:
    credentials_exception = HTTPException(status_code=401,detail="could not validate credentials",
    headers ={"WWW-authenticate":"Bearer"},
    )
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception
    username: str = payload.get("sub")
    if username is None:
        raise credentials_exception
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception
    return user

class QueryRequest(BaseModel):
    query: str
    session_id: str = None

class MessageUpdateRequest(BaseModel):
    analysis: dict = None
    visual_spec: dict = None

class AnalyzeDataRequest(BaseModel):
    query: str
    data: list[dict]
    message_id: int = None

class UserCreate(BaseModel):
    username : str
    password : str
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
    print("Initializing Database...")
    await init_db()
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

async def run_pipeline(query: str, history: list = None, message_id: int = None, allowed_access: list = None) -> dict:
    # Step 0: Intent Classification (NLI)
    classifier = get_nli_classifier()
    valid_intent = "A question about Enterprise ERP database data, procurement, purchase orders, items, or suppliers, analytical queries for procurement data, material management, inventory "
    fallback_intent = "A general conversational question, small talk, weather, stock market, or unrelated topic."
    candidate_labels = [valid_intent, fallback_intent]
    
    # Run the classification
    nli_result = classifier(query, candidate_labels)
    top_intent = nli_result['labels'][0]
    
    valid_index = nli_result['labels'].index(valid_intent)
    valid_score = nli_result['scores'][valid_index]
    
    print(f"\n[NLI INTENT] Query: '{query}'")
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
        query, 
        return_response=True,
        history=history,
        message_id=message_id
    )
    
    usage = response_obj.usage_metadata
    in_tok = getattr(usage, "prompt_token_count", 0)
    out_tok = getattr(usage, "candidates_token_count", 0)
    
    # Step 2: Validate SQL
    is_valid, final_sql, retry_in, retry_out = await validate_and_fix_sql(
        sql_raw, 
        query, 
        chat=chat,
        message_id=message_id,
        allowed_access=allowed_access
    )
    in_tok += retry_in
    out_tok += retry_out
    
    if not is_valid:
        if final_sql.startswith("AUTH_ERROR:"):
            return {
                "status": "error",
                "explanation": final_sql.replace("AUTH_ERROR: ", ""),
                "sql": None,
                "original_sql": sql_raw,
                "data": [],
                "cost": calculate_cost(in_tok, out_tok)
            }
        raise HTTPException(status_code=400, detail="Query validation failed. Unable to safely generate SQL.")
        
    # Step 3: Execute SQL
    if not conn_str or conn_str == "your_sql_server_connection_string":
        raise HTTPException(status_code=500, detail="Database connection string not configured.")
        
    columns, rows = execute_query(final_sql, connection_string=conn_str, message_id=message_id)
    
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

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from logger import create_log_sync, update_log_sync, log_error_sync

@app.post("/api/ask")
async def ask_question(request_model: QueryRequest, request: Request,current_user:User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        session_id = request_model.session_id
        if not session_id:
            # Create a new session if none provided
            session_id = str(uuid.uuid4())
            new_session = Session(id=session_id,user_id = current_user.id, title="New Chat")
            db.add(new_session)
            await db.commit()
        else:
            # Fetch the session 
            sess_result = await db.execute(select(Session).where(Session.id == session_id, Session.user_id==current_user.id))
            sess = sess_result.scalar_one_or_none()
            if not sess:
                raise HTTPException(status_code=403, detail="Not Authorized to access this session")
                
        from sqlalchemy.orm import defer
        # Fetch history from DB without loading heavy JSON columns
        result = await db.execute(
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.id)
            .options(
                defer(Message.data),
                defer(Message.cost),
                defer(Message.analysis),
                defer(Message.visual_spec)
            )
        )
        messages = result.scalars().all()
        
        # If this is the first message in the session, update the session title
        if not messages and session_id:
            sess_result = await db.execute(select(Session).where(Session.id == session_id))
            sess = sess_result.scalar_one_or_none()
            if sess:
                words = request_model.query.split()
                sess.title = " ".join(words[:6]) + ("..." if len(words) > 6 else "")
                await db.commit()
        
        successfulPairs = []
        currentUserMsg = None
        for msg in messages:
            if msg.role == 'user':
                currentUserMsg = msg.content
            elif msg.role == 'assistant' and msg.type == 'success' and currentUserMsg:
                successfulPairs.append({"question": currentUserMsg, "sql": msg.sql})
                currentUserMsg = None
                
        history = successfulPairs[-3:] # Sliding window
        
        # Save user message to DB
        user_msg = Message(session_id=session_id, role="user", content=request_model.query)
        db.add(user_msg)
        await db.commit()
        await db.refresh(user_msg)
        
        # Initiate the single-row log trace for this query
        create_log_sync(session_id, user_msg.id, request_model.query)

        # Fetch RoleTableAccess for current_user
        from database import RoleTableAccess
        role_id = current_user.role_id
        allowed_access = []
        if role_id is not None:
            access_result = await db.execute(select(RoleTableAccess).where(RoleTableAccess.role_id == role_id))
            access_records = access_result.scalars().all()
            for acc in access_records:
                allowed_access.append({
                    "table_name": acc.table_name.lower(),
                    "restricted_columns": json.loads(acc.restricted_columns) if acc.restricted_columns else []
                })

        # Wrap the whole pipeline in an asyncio task
        pipeline_task = asyncio.create_task(run_pipeline(request_model.query, history, user_msg.id, allowed_access))
        
        # Poll for client disconnect
        while not pipeline_task.done():
            if await request.is_disconnected():
                pipeline_task.cancel()
                print("\n[NVIDIA PIPELINE] 🛑 Request aborted by client disconnect!")
                return {}
            await asyncio.sleep(0.5)
            
        result_data = await pipeline_task
        
        from decimal import Decimal
        from datetime import datetime, date
        def json_serial(obj):
            if isinstance(obj, Decimal):
                return float(obj)
            if isinstance(obj, (datetime, date)):
                return obj.isoformat()
            raise TypeError(f"Type {type(obj)} not serializable")

        # Save assistant message to DB
        asst_msg = Message(
            session_id=session_id,
            role="assistant",
            type=result_data.get("status"),
            query=request_model.query,
            content=result_data.get("explanation") if result_data.get("status") == "error" else None,
            sql=result_data.get("sql"),
            original_sql=result_data.get("original_sql"),
            explanation=result_data.get("explanation") if result_data.get("status") == "success" else None,
            data=json.dumps(result_data.get("data"), default=json_serial) if result_data.get("data") is not None else None,
            cost=json.dumps(result_data.get("cost"), default=json_serial) if result_data.get("cost") is not None else None
        )
        db.add(asst_msg)
        await db.commit()
        await db.refresh(asst_msg)
        
        result_data["message_id"] = asst_msg.id
        result_data["session_id"] = session_id
        return result_data
        
    except asyncio.CancelledError:
        print(f"\n[NVIDIA PIPELINE] 🛑 Request aborted by client!")
        raise
    except Exception as e:
        print(f"\n[NVIDIA PIPELINE] 💥 UNEXPECTED ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/analyze")
async def analyze_data(request_model: AnalyzeDataRequest):
    if not request_model.data:
        return {"status": "error", "type": "error", "content": "No data provided for analysis."}
        
    df = pd.DataFrame(request_model.data)
    result = await generate_analytical_summary(df, request_model.query, message_id=request_model.message_id)
    return result

@app.post("/api/analyze_v2")
async def analyze_data_v2(request_model: AnalyzeDataRequest):
    if not request_model.data:
        return {"status": "error", "type": "error", "content": "No data provided for visual analysis."}
        
    df = pd.DataFrame(request_model.data)
    result = await generate_visual_summary(df, request_model.query, message_id=request_model.message_id)
    return result

@app.get("/api/sessions")
async def get_sessions(current_user:User = Depends(get_current_user),db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Session).where(Session.user_id==current_user.id).order_by(Session.created_at.desc()))
    sessions = result.scalars().all()
    return [{"id": s.id, "title": s.title, "date": s.created_at.isoformat()} for s in sessions]

@app.post("/api/sessions")
async def create_session(current_user:User = Depends(get_current_user),db: AsyncSession = Depends(get_db)):
    session_id = str(uuid.uuid4())
    new_session = Session(id=session_id, user_id=current_user.id, title="New Chat")
    db.add(new_session)
    await db.commit()
    return {"id": session_id, "title": "New Chat"}

@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str,current_user:User=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Session).where(Session.id == session_id, Session.user_id == current_user.id))
    sess = result.scalar_one_or_none()
    if not sess:
        raise HTTPException(status_code=404,detail="session not found")
    await db.execute(delete(Message).where(Message.session_id == session_id))
    await db.execute(delete(Session).where(Session.id == session_id))
    await db.commit()
    return {"status":"success"}

@app.get("/api/sessions/{session_id}/messages")
async def get_session_messages(session_id: str,current_user:User=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Session).where(Session.id == session_id,Session.user_id == current_user.id))
    sess = result.scalar_one_or_none()
    if not sess:
        raise HTTPException(status_code=404,detail="session not found") 
    result = await db.execute(select(Message).where(Message.session_id == session_id).order_by(Message.id))
    messages = result.scalars().all()
    return [msg.to_dict() for msg in messages]

@app.put("/api/messages/{message_id}")
async def update_message(message_id: int, request_model: MessageUpdateRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Message).where(Message.id == message_id))
    msg = result.scalar_one_or_none()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
        
    if request_model.analysis is not None:
        msg.analysis = json.dumps(request_model.analysis)
    if request_model.visual_spec is not None:
        msg.visual_spec = json.dumps(request_model.visual_spec)
        
    await db.commit()
    return {"status": "success"}

@app.post("/api/auth/register")
async def register_user(user_data:UserCreate,db:AsyncSession=Depends(get_db)):
    result = await db.execute(select(User).where(User.username==user_data.username))
    existing_user = result.scalar_one_or_none()
    if existing_user:
        raise HTTPException(status_code=400,detail="Username already registered")
    hashed_pwd = get_password_hash(user_data.password)
    new_user = User(username=user_data.username, hashed_password=hashed_pwd)
    db.add(new_user)
    await db.commit()
    return {"status":"success","message":"User registered successfully"}

@app.post("/api/auth/login")
async def login_user(user_data:UserCreate, db:AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == user_data.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(user_data.password,user.hashed_password):
        raise HTTPException(status_code = 401,detail="Incorrect username or password")
    access_token = create_access_token(data={"sub":user.username})
    return {"access_token":access_token,"token_type":"bearer"}
if __name__ == "__main__":
    import uvicorn
    import json
    import os

    config_path = os.path.join(os.path.dirname(__file__), "server_config.json")
    try:
        with open(config_path, "r") as f:
            config = json.load(f)
    except FileNotFoundError:
        config = {"host": "0.0.0.0", "port": 8000, "reload": True, "workers": 1}

    uvicorn.run(
        "main:app",
        host=config.get("host", "0.0.0.0"),
        port=config.get("port", 8000),
        reload=config.get("reload", True),
        workers=config.get("workers", 1)
    )
