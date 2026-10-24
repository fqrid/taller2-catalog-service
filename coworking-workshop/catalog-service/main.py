from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI(
    title="Catalog Service",
    description="Servicio de catálogo de espacios de coworking",
    version="1.0.0"
)

class Space(BaseModel):
    id: int
    name: str
    description: str
    capacity: int
    price_per_hour: float  # NOTA LAB 5: En Lab 5 se renombra a hourly_rate para romper contrato
    available: bool

# Base de datos simulada en memoria
SPACES_DB = [
    {
        "id": 1,
        "name": "Hot Desk Flexible",
        "description": "Puesto individual en zona abierta con wifi de alta velocidad",
        "capacity": 1,
        "price_per_hour": 15.0,
        "available": True
    },
    {
        "id": 2,
        "name": "Oficina Privada Ejecutiva",
        "description": "Espacio cerrado para equipos de 4 personas con pantalla y pizarra",
        "capacity": 4,
        "price_per_hour": 45.0,
        "available": True
    },
    {
        "id": 3,
        "name": "Sala de Juntas Innovación",
        "description": "Sala para conferencias equipada con proyector y sistema de videollamada",
        "capacity": 10,
        "price_per_hour": 75.0,
        "available": True
    }
]

@app.get("/health", summary="Verificar estado de salud del servicio")
def health_check():
    return {"status": "ok", "service": "catalog-service"}

@app.get("/spaces", summary="Listar todos los espacios de coworking")
def get_spaces():
    return SPACES_DB

@app.get("/spaces/{space_id}", summary="Consultar espacio por ID")
def get_space(space_id: int):
    space = next((s for s in SPACES_DB if s["id"] == space_id), None)
    if not space:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Space with id {space_id} not found"
        )
    return space

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
