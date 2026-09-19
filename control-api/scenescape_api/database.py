import os
from datetime import datetime, timezone
from urllib.parse import quote_plus
from sqlalchemy import JSON, DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

class Base(DeclarativeBase): pass
_engine=None; _Session=None
def utcnow(): return datetime.now(timezone.utc)
def database_url():
    explicit=os.getenv("DATABASE_URL")
    if explicit: return explicit
    host=os.getenv("DBHOST")
    if not host: return "sqlite:///./scenescape-native.db"
    user=quote_plus(os.getenv("DBUSER","scenescape")); password=quote_plus(os.getenv("DBPASSWORD","")); db=quote_plus(os.getenv("DBNAME","scenescape")); port=os.getenv("DBPORT","5432")
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db}"
class Resource(Base):
    __tablename__="native_resources"; id:Mapped[int]=mapped_column(Integer,primary_key=True); kind:Mapped[str]=mapped_column(String(40),index=True); uid:Mapped[str]=mapped_column(String(96),index=True); revision:Mapped[int]=mapped_column(Integer,default=1); payload:Mapped[dict]=mapped_column(JSON,default=dict); updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
class Observation(Base):
    __tablename__="native_observations"; id:Mapped[int]=mapped_column(Integer,primary_key=True); scene_id:Mapped[str]=mapped_column(String(96),index=True); topic:Mapped[str]=mapped_column(Text); observed_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),index=True); payload:Mapped[dict]=mapped_column(JSON)
class Event(Base):
    __tablename__="native_events"; id:Mapped[int]=mapped_column(Integer,primary_key=True); scene_id:Mapped[str]=mapped_column(String(96),index=True); topic:Mapped[str]=mapped_column(Text); observed_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),index=True); payload:Mapped[dict]=mapped_column(JSON)
class Incident(Base):
    __tablename__="native_incidents"; id:Mapped[int]=mapped_column(Integer,primary_key=True); event_id:Mapped[int|None]=mapped_column(Integer,nullable=True); scene_id:Mapped[str]=mapped_column(String(96),index=True); title:Mapped[str]=mapped_column(String(240)); status:Mapped[str]=mapped_column(String(32),default="new"); assignee:Mapped[str]=mapped_column(String(160),default=""); notes:Mapped[list]=mapped_column(JSON,default=list); audit:Mapped[list]=mapped_column(JSON,default=list); updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
class Heartbeat(Base):
    __tablename__="native_heartbeats"; key:Mapped[str]=mapped_column(String(64),primary_key=True); state:Mapped[str]=mapped_column(String(32)); details:Mapped[dict]=mapped_column(JSON,default=dict); updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
def get_engine():
    global _engine,_Session
    url=database_url()
    if _engine is None or str(_engine.url)!=url:
        connect_args={"check_same_thread":False} if url.startswith("sqlite") else {}
        _engine=create_engine(url,future=True,pool_pre_ping=True,connect_args=connect_args); _Session=sessionmaker(bind=_engine,expire_on_commit=False)
    return _engine
def sessions(): get_engine(); return _Session
