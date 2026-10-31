import os
import time
import logging
from datetime import datetime
import enum
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Enum as SQLEnum, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("database")

POSTGRES_URL_DEFAULT = "postgresql://orders_db_srhr_user:feXWf1AMw1bFY2oqggbUTzSwrtp9zrRv@dpg-dbj41q942hec73bvl9mg-a.ohio-postgres.render.com/orders_db_srhr"
DATABASE_URL = os.getenv("POSTGRES_URL") or os.getenv("DATABASE_URL") or POSTGRES_URL_DEFAULT

# Manejo de conexiones con Connection Pool y Retry
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False}
    )
else:
    # Manejo de URLs con esquema 'postgres://' o 'postgresql://' a 'postgresql+psycopg2://'
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)
    elif DATABASE_URL.startswith("postgresql://"):
        DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)
        
    engine = create_engine(
        DATABASE_URL,
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=1800,
        pool_pre_ping=True  # Verifica si la conexión está viva antes de entregarla del pool
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class OrderStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class User(Base):
    """Modelo de usuarios para PostgreSQL RDS"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Order(Base):
    """Modelo de órdenes de coworking para PostgreSQL RDS"""
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(255), index=True, nullable=False) # Email o ID de usuario
    space_id = Column(Integer, index=True, nullable=True)
    space_name = Column(String(255), nullable=True)
    hours = Column(Integer, default=1)
    price_per_hour = Column(Float, nullable=True)
    total = Column(Float, nullable=False)
    status = Column(SQLEnum(OrderStatus), default=OrderStatus.PENDING)
    created_at = Column(DateTime, default=datetime.utcnow)

def get_db():
    """Generador de sesiones para inyección de dependencias en FastAPI"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def check_db_connection(max_retries: int = 3, delay: int = 2) -> bool:
    """Verifica conexión con la base de datos con reintentos (retry)"""
    for attempt in range(1, max_retries + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("Conexión exitosa a PostgreSQL RDS.")
            return True
        except OperationalError as err:
            logger.warning(f"Intento {attempt}/{max_retries} fallido al conectar con PostgreSQL: {err}")
            if attempt < max_retries:
                time.sleep(delay)
    return False