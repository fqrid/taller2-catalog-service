import os
import logging
from datetime import datetime
from typing import Any, Dict
import requests
from fastapi import FastAPI, BackgroundTasks, status

# Configuración básica de logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Catalog & Consumer Service",
    description="Web Service consolidado para eventos de catálogo y procesamiento asíncrono hacia Orders Service",
    version="1.0.0"
)

ORDERS_SERVICE_URL = os.environ.get("ORDERS_SERVICE_URL", "http://orders-service.local/api/orders")


def send_event_to_orders_service(payload: Dict[str, Any]):
    """
    Tarea en segundo plano que simula el consumidor de eventos original.
    Envía el evento HTTP directamente hacia la URL definida en ORDERS_SERVICE_URL.
    """
    target_url = os.environ.get("ORDERS_SERVICE_URL", ORDERS_SERVICE_URL)
    logger.info(f"[{datetime.now()}] Procesando evento SpaceChanged en segundo plano: {payload}")
    
    try:
        response = requests.post(
            target_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        logger.info(
            f"Notificación exitosa a orders-service en {target_url} - Status: {response.status_code} - Respuesta: {response.text}"
        )
    except Exception as e:
        logger.error(f"Error al comunicar con orders-service en {target_url}: {str(e)}")


@app.get("/health", summary="Verificar estado de salud del servicio")
def health_check():
    return {
        "status": "ok",
        "service": "catalog-web-service",
        "orders_service_url": os.environ.get("ORDERS_SERVICE_URL", ORDERS_SERVICE_URL)
    }


@app.post("/catalog", status_code=status.HTTP_200_OK, summary="Recibir evento del catálogo")
async def receive_catalog_event(payload: Dict[str, Any], background_tasks: BackgroundTasks):
    """
    Endpoint que recibe el payload del catálogo y encola su procesamiento
    en segundo plano simulando la arquitectura asíncrona de eventos.
    """
    background_tasks.add_task(send_event_to_orders_service, payload)
    return {
        "message": "Evento recibido y encolado para procesamiento en segundo plano",
        "payload": payload
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
