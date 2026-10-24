import os
from datetime import datetime
from typing import List, Optional
import httpx
from fastapi import FastAPI, HTTPException, Query, status
from pydantic import BaseModel, EmailStr

app = FastAPI(
    title="Orders Service",
    description="Servicio de órdenes y reservas de espacios de coworking",
    version="1.0.0"
)

# URL del catalog-service configurable por variable de entorno
CATALOG_SERVICE_URL = os.getenv("CATALOG_SERVICE_URL", "http://localhost:8001")

class Order(BaseModel):
    id: int
    space_id: int
    space_name: str
    user_email: str
    hours: int
    price_per_hour: float
    total_amount: float
    status: str
    created_at: str

# Base de datos simulada en memoria
ORDERS_DB = []

@app.get("/health", summary="Verificar estado de salud del servicio")
def health_check():
    return {"status": "ok", "service": "orders-service"}

@app.post("/orders", summary="Crear una nueva orden de reserva")
async def create_order(
    space_id: int = Query(..., description="ID del espacio a reservar"),
    user_email: str = Query(..., description="Correo del usuario"),
    hours: int = Query(..., ge=1, description="Horas de reserva")
):
    # 1. Consultar catalog-service vía HTTP
    catalog_endpoint = f"{CATALOG_SERVICE_URL}/spaces/{space_id}"
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            response = await client.get(catalog_endpoint)
    except (httpx.RequestError, httpx.ConnectError, httpx.TimeoutException) as exc:
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
    # NOTA LAB 5: orders-service espera obligatoriamente space["price_per_hour"].
    # Si catalog-service renombra este campo a 'hourly_rate', fallará aquí con KeyError (rompimiento de contrato).
    try:
        price_per_hour = space["price_per_hour"]
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Contract violation: Missing expected 'price_per_hour' field in catalog response"
        )

    total_amount = round(price_per_hour * hours, 2)

    new_order = {
        "id": len(ORDERS_DB) + 1,
        "space_id": space_id,
        "space_name": space.get("name", "Unknown Space"),
        "user_email": user_email,
        "hours": hours,
        "price_per_hour": price_per_hour,
        "total_amount": total_amount,
        "status": "confirmed",
        "created_at": datetime.utcnow().isoformat()
    }
    ORDERS_DB.append(new_order)
    return new_order

@app.get("/orders", summary="Listar todas las órdenes")
def get_orders():
    return ORDERS_DB

@app.get("/orders/{order_id}", summary="Consultar orden por ID")
def get_order(order_id: int):
    order = next((o for o in ORDERS_DB if o["id"] == order_id), None)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order with id {order_id} not found"
        )
    return order

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8002, reload=True)
