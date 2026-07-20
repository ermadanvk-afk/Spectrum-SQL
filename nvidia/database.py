import json
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, relationship
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
    session_id = Column(String, ForeignKey("sessions.id"))
    role = Column(String)  # 'user' or 'assistant'
    type = Column(String)  # 'success', 'error', etc.
    content = Column(Text, nullable=True)
    query = Column(Text, nullable=True)
    sql = Column(Text, nullable=True)
    original_sql = Column(Text, nullable=True)
    explanation = Column(Text, nullable=True)
    data = Column(Text, nullable=True)
    cost = Column(Text, nullable=True)
    analysis = Column(Text, nullable=True)
    visual_spec = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    db_id = Column(Integer, ForeignKey("db_master.id"), nullable=True)

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
            "db_id": self.db_id,
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
    hashed_password = Column(String(255), nullable=False)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=True)
    display_token = Column(Boolean, default=False)
    display_sql = Column(Boolean, default=False)
    user_type = Column(Integer, default=2) # 1 = Admin, 2 = General User
    is_active = Column(Boolean, default=True)
    
    role = relationship("Role", back_populates="users")
    database_access = relationship("UserDatabaseAccess", back_populates="user", cascade="all, delete")

class Role(Base):
    __tablename__ = "roles"
    id = Column(Integer,primary_key=True, index=True,autoincrement=True)
    name = Column(String,unique=True,index=True,nullable = False)
    users = relationship("User",back_populates="role")
    table_permissions = relationship("RoleTableAccess",back_populates="role",cascade="all, delete")

class RoleTableAccess(Base):
    __tablename__ = "role_table_access"
    id = Column(Integer,primary_key=True,index=True,autoincrement=True)
    role_id = Column(Integer,ForeignKey("roles.id"),nullable=False)
    table_name = Column(String,nullable=False)
    restricted_columns = Column(Text,nullable=True)
    role = relationship("Role",back_populates="table_permissions")

class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token = Column(String, unique=True, index=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    revoked = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User")

class DBMaster(Base):
    __tablename__ = "db_master"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String, unique=True, index=True, nullable=False)
    connection_string = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    users = relationship("UserDatabaseAccess", back_populates="db", cascade="all, delete")

class UserDatabaseAccess(Base):
    __tablename__ = "user_database_access"
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True, nullable=False)
    db_id = Column(Integer, ForeignKey("db_master.id"), primary_key=True, nullable=False)
    
    user = relationship("User", back_populates="database_access")
    db = relationship("DBMaster", back_populates="users")