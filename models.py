from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, text, DateTime, Boolean, Text

automator_path = "/home/cptlab3/btl-production/automator"
#DATABASE_URL = "sqlite+aiosqlite:////home/cmsdaq/DAQ/automator/runs.db"
DATABASE_URL = f"sqlite+aiosqlite:///{automator_path}/runs.db"
Base = declarative_base()
engine = create_async_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

# -----------------------------
# DB Model
# -----------------------------
class Run(Base):
    __tablename__ = "runs"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    Tray = Column(String, default="MTD-TrayNULL")
    date = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
    RU = Column(Integer)
    run_type = Column(String)
    run_number = Column(Integer, nullable=True)  # allow null
    status = Column(String)  # queued, processing, completed, failed on serenity
    stdout = Column(Text, default="")
    stderr = Column(Text, default="")
    plot_link = Column(String, default="#")
    serenity_stdout = Column(Text, default="")  # new
    serenity_stderr = Column(Text, default="")  # new

class Tray(Base):
    __tablename__ = "trays"
    label = Column(String, primary_key=True)
    RU0 = Column(Boolean, default=True)
    RU1 = Column(Boolean, default=True)
    RU2 = Column(Boolean, default=True)
    RU3 = Column(Boolean, default=True)
    RU4 = Column(Boolean, default=True)
    RU5 = Column(Boolean, default=True)
