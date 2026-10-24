# Informe Técnico: Taller de Microservicios y Chaos Engineering

**Sistema de Reserva de Espacios de Coworking**  
**Fecha:** 17 de Octubre de 2026  
**Tecnologías:** FastAPI, Python 3.11, Docker, Docker Compose, Chaos Engineering, Postman / cURL  

---

## 1. Introducción y Objetivo General
El presente documento describe el diseño, despliegue y validación de una arquitectura distribuida basada en microservicios, así como la aplicación práctica de pruebas de **Chaos Engineering**. 

El objetivo principal fue evaluar la resiliencia del sistema ante fallos reales de infraestructura (caída repentina de un servicio dependiente) y cambios no consensuados en contratos de API (*breaking changes*).

---

## 2. Arquitectura de la Solución

El sistema se compone de dos microservicios autónomos desplegados en contenedores Docker y conectados mediante una red virtual de tipo bridge (`coworking_coworking-network`):

```text
+-----------------------+                    +---------------------+
|    catalog-service    | <--- HTTP Síncrono |    orders-service   |
|   (FastAPI / :8001)   |   (Red de Docker)  |  (FastAPI / :8002)  |
+-----------------------+                    +---------------------+
           |                                            |
           +--------------------+-----------------------+
                                |
                    [ Red Virtual de Docker ]
                 (coworking_coworking-network)
```

1. **`catalog-service` (Puerto 8001):**
   - Microservicio encargado del catálogo de espacios de trabajo (Hot Desks, Oficinas Privadas, Salas de Juntas).
   - Expone endpoints para verificar salud (`/health`), listar espacios (`/spaces`) y consultar por identificador (`/spaces/{id}`).
2. **`orders-service` (Puerto 8002):**
   - Microservicio encargado de registrar y listar órdenes de reserva de usuarios.
   - Para confirmar una orden, consume internamente al `catalog-service` a través de HTTP (`httpx`), valida la existencia del espacio, obtiene su tarifa por hora y calcula el costo total.

---

## 3. Desarrollo Detallado por Laboratorio y Evidencias

---

### LAB 1: `catalog-service` con FastAPI (Prueba Local)
* **Objetivo:** Crear un microservicio independiente que exponga espacios de coworking vía HTTP en el puerto `8001`.
* **Archivos implementados:**
  - `catalog-service/main.py`: Lógica de endpoints (`/health`, `/spaces`, `/spaces/{id}`).
  - `catalog-service/requirements.txt`: `fastapi`, `uvicorn[standard]`, `pydantic`.
  - `catalog-service/Dockerfile`: Imagen base `python:3.11-slim`.
* **Comandos de ejecución local:**
  ```bash
  cd catalog-service
  source ../venv/bin/activate
  python main.py
  ```
* **Pruebas en otra terminal:**
  ```bash
  curl http://localhost:8001/health
  curl http://localhost:8001/spaces
  curl http://localhost:8001/spaces/1
  ```
* **Resultado:**
  - El servidor Uvicorn arranca en `http://0.0.0.0:8001`.
  - `/health` responde `{"status": "ok", "service": "catalog-service"}`.
  - `/spaces` entrega la lista con los 3 tipos de puestos y precios.
  - `/spaces/1` entrega el detalle del puesto individual ($15.0/h).
* *[Insertar aquí Captura LAB 1: Terminal con Uvicorn en 8001 y curls de prueba]*

---

### LAB 2: `orders-service` que consulta al Catálogo (Prueba Local)
* **Objetivo:** Crear el servicio de órdenes que dependa e interactúe con el catálogo vía HTTP.
* **Archivos implementados:**
  - `orders-service/main.py`: Endpoints de órdenes y cliente HTTP asíncrono con `httpx`.
  - `orders-service/requirements.txt`: `fastapi`, `uvicorn[standard]`, `pydantic`, `httpx`.
  - `orders-service/Dockerfile`: Imagen base `python:3.11-slim`.
* **Comandos de ejecución local:**
  ```bash
  cd orders-service
  source ../venv/bin/activate
  python main.py
  ```
* **Prueba en terminal:**
  ```bash
  curl http://localhost:8002/health
  ```
* **Resultado:**
  - Uvicorn arranca en `http://0.0.0.0:8002`.
  - `/health` responde `{"status": "ok", "service": "orders-service"}`.
* *[Insertar aquí Captura LAB 2: Terminal con orders-service y curl /health]*

---

### LAB 3: Docker Compose con Red Compartida
* **Objetivo:** Orquestar ambos servicios en contenedores Docker comunicándose a través de una red virtual privada sin acoplar direcciones IP fijas.
* **Archivo implementado:** `docker-compose.yml` (definiendo la red bridge `coworking_coworking-network` y la variable de entorno `CATALOG_SERVICE_URL=http://catalog-service:8001`).
* **Comandos ejecutados:**
  ```bash
  docker compose up -d
  curl http://localhost:8001/spaces
  curl -X POST "http://localhost:8002/orders?space_id=1&user_email=test@example.com&hours=2"
  curl http://localhost:8002/orders
  ```
* **Resultado:**
  - Ambos contenedores se levantan en segundo plano.
  - Al solicitar la orden a `orders-service` (:8002), este resuelve por DNS interno al `catalog-service` (:8001), extrae el precio y calcula el total de $30.0 de forma transparente.
* *[Insertar aquí Captura LAB 3: docker compose up -d y flujo de creación de orden]*

---

### LAB 4: Chaos Engineering - Apagar el Catálogo (Caída de Dependencia)
* **Objetivo:** Evaluar la resiliencia y el comportamiento del sistema ante la desconexión abrupta de la dependencia síncrona.
* **Comandos ejecutados:**
  ```bash
  # 1. Apagado del catálogo
  docker compose stop catalog-service

  # 2. Intento de creación de orden
  curl -i -X POST "http://localhost:8002/orders?space_id=1&user_email=test@example.com&hours=2"

  # 3. Restauración
  docker compose start catalog-service
  sleep 3

  # 4. Verificación de recuperación
  curl -X POST "http://localhost:8002/orders?space_id=1&user_email=test@example.com&hours=2"
  ```
* **Resultado y Observaciones:**
  1. Con catálogo apagado: El servicio no colapsa ni lanza excepciones no controladas. Retorna **`HTTP 503 Service Unavailable`** con `{"detail":"Catalog service unavailable"}`.
  2. Tras la recuperación: `orders-service` reanuda de inmediato la confirmación de órdenes con **`200 OK`** sin requerir reinicio (servicio *stateless*).
* *[Insertar aquí Captura LAB 4: Script chaos-test.sh o prueba manual con error 503 y recuperación]*

---

### LAB 5: Chaos Engineering - Cambiar el Contrato sin Avisar (Breaking Change)
* **Objetivo:** Simular la rotura de integración provocada por una modificación no consensuada en el esquema JSON de la API proveedora.
* **Comandos ejecutados:**
  ```bash
  # 1. Modificar catálogo cambiando "price_per_hour" por "hourly_rate"
  sed -i '' 's/"price_per_hour":/"hourly_rate":/g' catalog-service/main.py

  # 2. Reconstruir contenedor de catálogo
  docker compose up --build -d catalog-service
  sleep 4

  # 3. Probar solicitud
  curl -i -X POST "http://localhost:8002/orders?space_id=1&user_email=contract@test.com&hours=2"

  # 4. Restauración del contrato original
  sed -i '' 's/"hourly_rate":/"price_per_hour":/g' catalog-service/main.py
  docker compose up --build -d catalog-service
  ```
* **Resultado:**
  - La petición falla con **`HTTP 500 Internal Server Error`** (*"Contract violation: Missing expected 'price_per_hour' field"*).
  - Ambos servicios se encuentran físicamente encendidos, pero la integración de negocio queda interrumpida.
* *[Insertar aquí Captura LAB 5: Error 500 por violación de contrato y restauración exitosa]*

---

## 4. Análisis de Chaos Engineering y Lecciones Aprendidas

### 1. Caída de Servicios Dependientes
- **Riesgo:** Si un servicio dependiente falla y el llamador no maneja timeouts ni excepciones, los hilos se saturan provocando fallos en cascada en toda la infraestructura.
- **Buena práctica:** Implementar timeouts estrictos (`timeout=4.0s`) y traducir excepciones de red a respuestas semánticas estándar como **HTTP 503**.

### 2. Cambios de Contrato sin Versionamiento
- **Causa raíz:** Acoplamiento rígido al formato del JSON sin versionar ni validar esquemas.
- **Soluciones arquitectónicas:**
  1. **Versionamiento de APIs:** Implementar prefijos de versión (`/v1/spaces` vs `/v2/spaces`).
  2. **Período de Retrocompatibilidad:** Exponer temporalmente ambos atributos (`price_per_hour` y `hourly_rate`) mientras los consumidores migran.
  3. **Consumer-Driven Contract Testing:** Integrar herramientas como **Pact** en el pipeline de CI/CD para bloquear despliegues que rompan contratos vigentes.

---

## 5. Conclusiones Generales
1. **Orquestación con Docker:** La red bridge compartida facilitó la comunicación interna mediante nombres DNS de servicio (`catalog-service`), desacoplando la infraestructura de IPs fijas.
2. **Resiliencia Demostrada:** Las pruebas de Chaos Engineering permitieron comprobar que `orders-service` aísla las fallas adecuadamente y se recupera de forma autónoma.
3. **Contratos Inmutables:** Los esquemas de datos entre microservicios deben ser tratados como contratos inmutables regidos por versionamiento semántico.
