import os
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, HTTPException, Query, status
from pydantic import BaseModel, Field

from mongodb_client import MongoDBAnalyticsClient

app = FastAPI(
    title="Analytics Service",
    description="Servicio de Analytics y Métricas de uso con MongoDB Atlas",
    version="1.0.0"
)

# Inicializar cliente de MongoDB Atlas
mongo_client = MongoDBAnalyticsClient()

class EventIn(BaseModel):
    event_type: str = Field(..., example="order_created")
    data: Dict[str, Any] = Field(default_factory=dict)
    user_id: Optional[str] = Field(None, example="user@example.com")
    space_id: Optional[int] = Field(None, example=1)

class EventResponse(BaseModel):
    status: str
    event_id: str

@app.get("/health", summary="Verificar estado de salud del servicio y conexión a MongoDB Atlas")
def health_check():
    connected = mongo_client.is_connected()
    return {
        "status": "ok" if connected else "degraded",
        "service": "analytics-service",
        "mongodb_atlas": "connected" if connected else "unreachable"
    }

@app.post("/events", response_model=EventResponse, status_code=status.HTTP_201_CREATED, summary="Registrar nuevo evento de analítica")
def ingest_event(event: EventIn):
    try:
        inserted_id = mongo_client.log_event(
            event_type=event.event_type,
            data=event.data,
            user_id=event.user_id,
            space_id=event.space_id
        )
        return {"status": "recorded", "event_id": inserted_id}
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Error al almacenar evento en MongoDB Atlas: {str(exc)}"
        )

@app.get("/analytics/summary", summary="Obtener métricas agregadas de reservas e ingresos")
def get_summary(days: int = Query(30, ge=1, le=365, description="Ventana de días para el resumen")):
    return mongo_client.get_order_summary_metrics(days=days)

@app.get("/analytics/popular-spaces", summary="Espacios de coworking con más reservas")
def get_popular_spaces(limit: int = Query(5, ge=1, le=50, description="Cantidad máxima de resultados")):
    return mongo_client.get_popular_spaces(limit=limit)

@app.get("/analytics/active-users", summary="Usuarios más activos en la ventana de tiempo")
def get_active_users(hours: int = Query(24, ge=1, le=720, description="Ventana de horas")):
    return mongo_client.get_active_users(hours=hours)

@app.get("/analytics/recent", summary="Obtener métricas de las últimas 24 horas (get_recent_metrics)")
def get_recent():
    return mongo_client.get_recent_metrics()

@app.get("/analytics/events", summary="Consultar log cronológico de eventos")
def get_events(limit: int = Query(20, ge=1, le=100, description="Número de eventos a recuperar")):
    return mongo_client.get_recent_events(limit=limit)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8003, reload=True)
