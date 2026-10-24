#!/bin/bash
# ==============================================================================
# Script de Chaos Engineering: Caída del servicio de Catálogo
# LAB 4 - coworking-workshop
# ==============================================================================

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${BLUE}======================================================${NC}"
echo -e "${BLUE}    CHAOS TEST: Caída de Servicio Dependiente        ${NC}"
echo -e "${BLUE}======================================================${NC}"

# Detectar comando docker-compose o docker compose
if command -v docker-compose &> /dev/null; then
    COMPOSE_CMD="docker-compose"
else
    COMPOSE_CMD="docker compose"
fi

# ------------------------------------------------------------------------------
# Paso 1: Petición inicial con el sistema saludable
# ------------------------------------------------------------------------------
echo -e "\n${CYAN}[PASO 1] Probando flujo normal con catalog-service ACTIVO...${NC}"
HTTP_RESPONSE_1=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -X POST "http://localhost:8002/orders?space_id=1&user_email=test@example.com&hours=2")
STATUS_1=$(echo "$HTTP_RESPONSE_1" | grep "HTTP_STATUS" | cut -d':' -f2)
BODY_1=$(echo "$HTTP_RESPONSE_1" | grep -v "HTTP_STATUS")

echo "Respuesta del servidor:"
echo "$BODY_1"
if [ "$STATUS_1" -eq 200 ]; then
    echo -e "${GREEN}✓ Observación 1: Éxito (HTTP $STATUS_1 OK) - Orden creada exitosamente.${NC}"
else
    echo -e "${RED}✗ Observación 1: Código inesperado (HTTP $STATUS_1). Verifique que los servicios estén levantados.${NC}"
fi

# ------------------------------------------------------------------------------
# Paso 2: Inducir fallo (apagar catalog-service)
# ------------------------------------------------------------------------------
echo -e "\n${YELLOW}[PASO 2] Introduciendo Caos: Apagando catalog-service...${NC}"
$COMPOSE_CMD stop catalog-service
sleep 2

# ------------------------------------------------------------------------------
# Paso 3: Probar con el catálogo caído
# ------------------------------------------------------------------------------
echo -e "\n${CYAN}[PASO 3] Probando creación de orden con catalog-service CAÍDO...${NC}"
HTTP_RESPONSE_2=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -X POST "http://localhost:8002/orders?space_id=1&user_email=test@example.com&hours=2")
STATUS_2=$(echo "$HTTP_RESPONSE_2" | grep "HTTP_STATUS" | cut -d':' -f2)
BODY_2=$(echo "$HTTP_RESPONSE_2" | grep -v "HTTP_STATUS")

echo "Respuesta del servidor:"
echo "$BODY_2"
if [ "$STATUS_2" -eq 503 ]; then
    echo -e "${GREEN}✓ Observación 2: Error 503 \"Catalog service unavailable\" detectado como se esperaba.${NC}"
else
    echo -e "${RED}✗ Observación 2: Se obtuvo HTTP $STATUS_2 en lugar de 503.${NC}"
fi

# ------------------------------------------------------------------------------
# Paso 4: Recuperación (restaurar catalog-service)
# ------------------------------------------------------------------------------
echo -e "\n${YELLOW}[PASO 4] Restaurando catalog-service...${NC}"
$COMPOSE_CMD start catalog-service
echo "Esperando a que catalog-service esté listo..."

# Esperar a que /health responda 200
for i in {1..10}; do
    HEALTH=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/health || true)
    if [ "$HEALTH" -eq 200 ]; then
        echo -e "${GREEN}catalog-service está en línea nuevamente.${NC}"
        break
    fi
    sleep 1
done

# ------------------------------------------------------------------------------
# Paso 5: Probar después de la recuperación
# ------------------------------------------------------------------------------
echo -e "\n${CYAN}[PASO 5] Probando creación de orden tras la RECUPERACIÓN...${NC}"
HTTP_RESPONSE_3=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -X POST "http://localhost:8002/orders?space_id=1&user_email=test@example.com&hours=2")
STATUS_3=$(echo "$HTTP_RESPONSE_3" | grep "HTTP_STATUS" | cut -d':' -f2)
BODY_3=$(echo "$HTTP_RESPONSE_3" | grep -v "HTTP_STATUS")

echo "Respuesta del servidor:"
echo "$BODY_3"
if [ "$STATUS_3" -eq 200 ]; then
    echo -e "${GREEN}✓ Observación 3: Éxito (HTTP $STATUS_3 OK) tras la recuperación.${NC}"
else
    echo -e "${RED}✗ Observación 3: Se obtuvo HTTP $STATUS_3 tras reiniciar catálogo.${NC}"
fi

echo -e "\n${BLUE}======================================================${NC}"
echo -e "${BLUE}             RESUMEN DEL EXPERIMENTO                  ${NC}"
echo -e "${BLUE}======================================================${NC}"
echo -e "1. Servicio Catálogo Saludable : HTTP $STATUS_1"
echo -e "2. Servicio Catálogo Detenido  : HTTP $STATUS_2"
echo -e "3. Servicio Catálogo Restaurado: HTTP $STATUS_3"
echo -e "${GREEN}Experimento de caos finalizado correctamente.${NC}\n"
