import os
import logging
from datetime import datetime
from typing import List, Optional
import httpx
from fastapi import FastAPI, HTTPException, Query, Depends, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from database import Base, engine, get_db, check_db_connection, Order as DBOrder, User as DBUser, OrderStatus

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("orders_service")

# Crear tablas si no existen (en producción se gestiona con Alembic)
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Orders Service",
    description="Servicio de órdenes y reservas de espacios de coworking conectado a PostgreSQL RDS",
    version="2.0.0"
)

# URLs de servicios colaboradores
CATALOG_SERVICE_URL = os.getenv("CATALOG_SERVICE_URL", "http://localhost:8001")
ANALYTICS_SERVICE_URL = os.getenv("ANALYTICS_SERVICE_URL", "http://localhost:8003")

# Modelos Pydantic para Serialización
class OrderResponse(BaseModel):
    id: int
    space_id: Optional[int]
    space_name: Optional[str]
    user_email: str
    hours: int
    price_per_hour: Optional[float]
    total_amount: float
    status: str
    created_at: str

    class Config:
        from_attributes = True

class UserCreate(BaseModel):
    email: EmailStr
    name: Optional[str] = None

class UserResponse(BaseModel):
    id: int
    email: str
    name: Optional[str]
    created_at: str

    class Config:
        from_attributes = True

async def send_analytics_event(event_type: str, data: dict, user_id: str, space_id: Optional[int] = None):
    """Envía un evento de analítica al microservicio analytics-service de forma no bloqueante."""
    try:
        payload = {
            "event_type": event_type,
            "data": data,
            "user_id": user_id,
            "space_id": space_id
        }
        async with httpx.AsyncClient(timeout=2.0) as client:
            await client.post(f"{ANALYTICS_SERVICE_URL}/events", json=payload)
    except Exception as e:
        logger.warning(f"No se pudo enviar evento a analytics-service ({e}), continuando operación...")

@app.get("/health", summary="Verificar estado de salud del servicio y PostgreSQL RDS")
def health_check():
    db_ok = check_db_connection(max_retries=1, delay=0)
    return {
        "status": "ok" if db_ok else "degraded",
        "service": "orders-service",
        "database": "connected" if db_ok else "unreachable"
    }

@app.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED, summary="Registrar usuario en PostgreSQL RDS")
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(DBUser).filter(DBUser.email == user.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="El usuario ya existe")
    new_user = DBUser(email=user.email, name=user.name)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {
        "id": new_user.id,
        "email": new_user.email,
        "name": new_user.name,
        "created_at": new_user.created_at.isoformat()
    }

@app.get("/users", response_model=List[UserResponse], summary="Listar usuarios en PostgreSQL RDS")
def list_users(db: Session = Depends(get_db)):
    users = db.query(DBUser).all()
    return [
        {
            "id": u.id,
            "email": u.email,
            "name": u.name,
            "created_at": u.created_at.isoformat()
        }
        for u in users
    ]

@app.post("/orders", response_model=OrderResponse, summary="Crear una nueva orden de reserva persistida en PostgreSQL")
async def create_order(
    space_id: int = Query(..., description="ID del espacio a reservar"),
    user_email: str = Query(..., description="Correo del usuario"),
    hours: int = Query(..., ge=1, description="Horas de reserva"),
    db: Session = Depends(get_db)
):
    # 1. Consultar catalog-service vía HTTP
    catalog_endpoint = f"{CATALOG_SERVICE_URL}/spaces/{space_id}"
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            response = await client.get(catalog_endpoint)
    except (httpx.RequestError, httpx.ConnectError, httpx.TimeoutException):
        # Fallo de comunicación distribuida (LAB 4)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Catalog service unavailable"
        )

    # 2. Validar respuesta del catálogo
    if response.status_code == status.HTTP_404_NOT_FOUND:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Space with id {space_id} not found in catalog"
        )
    elif response.status_code != status.HTTP_200_OK:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Catalog service unavailable"
        )

    space = response.json()

    # 3. Procesar datos del espacio y calcular total
    try:
        price_per_hour = space["price_per_hour"]
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Contract violation: Missing expected 'price_per_hour' field in catalog response"
        )

    total_amount = round(price_per_hour * hours, 2)
    space_name = space.get("name", "Unknown Space")

    # 4. Persistir orden en PostgreSQL RDS
    new_order = DBOrder(
        user_id=user_email,
        space_id=space_id,
        space_name=space_name,
        hours=hours,
        price_per_hour=price_per_hour,
        total=total_amount,
        status=OrderStatus.CONFIRMED,
        created_at=datetime.utcnow()
    )
    db.add(new_order)
    db.commit()
    db.refresh(new_order)

    # 5. Notificar asíncronamente a analytics-service (LAB 9)
    await send_analytics_event(
        event_type="order_created",
        data={
            "order_id": new_order.id,
            "space_id": space_id,
            "space_name": space_name,
            "user_email": user_email,
            "hours": hours,
            "price_per_hour": price_per_hour,
            "total_amount": total_amount
        },
        user_id=user_email,
        space_id=space_id
    )

    return {
        "id": new_order.id,
        "space_id": new_order.space_id,
        "space_name": new_order.space_name,
        "user_email": new_order.user_id,
        "hours": new_order.hours,
        "price_per_hour": new_order.price_per_hour,
        "total_amount": new_order.total,
        "status": new_order.status.value if hasattr(new_order.status, 'value') else str(new_order.status),
        "created_at": new_order.created_at.isoformat()
    }

@app.get("/orders", response_model=List[OrderResponse], summary="Listar todas las órdenes desde PostgreSQL")
def get_orders(db: Session = Depends(get_db)):
    orders = db.query(DBOrder).all()
    return [
        {
            "id": o.id,
            "space_id": o.space_id,
            "space_name": o.space_name,
            "user_email": o.user_id,
            "hours": o.hours,
            "price_per_hour": o.price_per_hour,
            "total_amount": o.total,
            "status": o.status.value if hasattr(o.status, 'value') else str(o.status),
            "created_at": o.created_at.isoformat()
        }
        for o in orders
    ]

@app.get("/orders/{order_id}", response_model=OrderResponse, summary="Consultar orden por ID desde PostgreSQL")
def get_order(order_id: int, db: Session = Depends(get_db)):
    order = db.query(DBOrder).filter(DBOrder.id == order_id).first()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order with id {order_id} not found"
        )
    return {
        "id": order.id,
        "space_id": order.space_id,
        "space_name": order.space_name,
        "user_email": order.user_id,
        "hours": order.hours,
        "price_per_hour": order.price_per_hour,
        "total_amount": order.total,
        "status": order.status.value if hasattr(order.status, 'value') else str(order.status),
        "created_at": order.created_at.isoformat()
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8002, reload=True)
