import json
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
db_path = os.path.join(BASE_DIR, 'spectrum.db').replace('\\', '/')
DATABASE_URL = f"sqlite+aiosqlite:///{db_path}"

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

Base = declarative_base()

class Session(Base):
    __tablename__ = "sessions"
    id = Column(String, primary_key=True, index=True)
    user_id = Column(Integer,ForeignKey("users.id"),nullable=True)
    title = Column(String, default="New Chat")
    created_at = Column(DateTime, default=datetime.utcnow)


class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    session_id = Column(String, index=True)
    role = Column(String) # 'user' or 'assistant'
    type = Column(String, nullable=True) # 'success' or 'error'
    query = Column(Text, nullable=True)
    content = Column(Text, nullable=True)
    sql = Column(Text, nullable=True)
    original_sql = Column(Text, nullable=True)
    explanation = Column(Text, nullable=True)
    data = Column(Text, nullable=True) # Stored as JSON string
    cost = Column(Text, nullable=True) # Stored as JSON string
    analysis = Column(Text, nullable=True) # Stored as JSON string
    visual_spec = Column(Text, nullable=True) # Stored as JSON string
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "session_id": self.session_id,
            "role": self.role,
            "type": self.type,
            "query": self.query,
            "content": self.content,
            "sql": self.sql,
            "original_sql": self.original_sql,
            "explanation": self.explanation,
            "data": json.loads(self.data) if self.data else None,
            "cost": json.loads(self.cost) if self.cost else None,
            "analysis": json.loads(self.analysis) if self.analysis else None,
            "visual_spec": json.loads(self.visual_spec) if self.visual_spec else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "isHistorical": True
        }

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
class User(Base): # user model added
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String,unique=True,index=True,nullable=False)
    hashed_password = Column(String,nullable=False)
