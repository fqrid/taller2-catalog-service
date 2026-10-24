# Informe de Chaos Engineering

## Resumen Ejecutivo
Este informe documenta los experimentos de Chaos Engineering realizados sobre la arquitectura de microservicios de Coworking (`catalog-service` y `orders-service`). Los experimentos evalúan la resiliencia ante caídas de dependencias síncronas HTTP y la tolerancia a fallos por cambios no consensuados en contratos de API (breaking changes).

---

## Test 1: Caída de servicio dependiente

* **Escenario**: 
  Detención abrupta del servicio `catalog-service` mediante `docker-compose stop catalog-service` mientras el servicio `orders-service` sigue en ejecución y recibiendo solicitudes entrantes para la creación de órdenes de reserva.

* **Impacto**: 
  - Las solicitudes a `POST /orders` no pueden consultar el precio ni la existencia del espacio solicitado.
  - Gracias al manejo de excepciones en `orders-service`, el servicio no colapsa ni lanza un error no controlado (500), sino que retorna un código **HTTP 503 Service Unavailable** con el mensaje `"Catalog service unavailable"`.
  - La falla queda aislada y controlada, evitando la propagación de fallos en cascada.

* **Tiempo de detección**: 
  - **Inmediato (< 100 ms)** en entornos con red local/Docker al fallar el handshake TCP, o acotado por el timeout del cliente HTTP (`timeout=4.0s`).

* **Recuperación**: 
  - Al ejecutar `docker-compose start catalog-service`, el servicio de catálogo se restablece y se vuelve saludable.
  - `orders-service` recupera inmediatamente su funcionalidad al 100% retornando **HTTP 200 OK** en la siguiente solicitud sin requerir reinicio, gracias a que el cliente HTTP es stateless.

---

## Test 2: Cambio de contrato sin versionar

* **Escenario**: 
  Modificación unilateral en `catalog-service` renombrando el atributo de precio de `price_per_hour` a `hourly_rate` en la respuesta JSON del endpoint `/spaces/{space_id}`, sin actualizar previamente a los servicios consumidores ni versionar el API.

* **Impacto**: 
  - Rotura inmediata del flujo de negocio en `orders-service`.
  - Al recibir la respuesta del catálogo, `orders-service` intenta acceder a la llave `space["price_per_hour"]` para calcular el monto total, desencadenando un fallo de contrato (`KeyError` / **HTTP 500 Internal Server Error**).
  - Los usuarios no pueden completar ninguna reserva a pesar de que ambos servicios se encuentran en estado "Up" y saludables según sus respectivos `/health`.

* **Causa raíz**: 
  - **Acoplamiento rígido de esquema**: Consumidor dependiente de nombres exactos de campos sin deserialización defensiva ni valores por defecto.
  - **Falta de versionamiento de API**: El proveedor modificó el esquema de un endpoint en producción/desarrollo sin introducir un nuevo prefijo de versión (`/v2/spaces`).
  - **Ausencia de pruebas de contrato (Consumer-Driven Contracts)**: Falta de validación en pipelines CI/CD que detecte inconsistencias entre lo que el consumidor espera y lo que el proveedor entrega.

* **Solución propuesta**: 
  1. **Versionamiento de APIs**: Implementar rutas versionadas (ejemplo: `/v1/spaces` conservando `price_per_hour` y `/v2/spaces` con `hourly_rate`).
  2. **Estrategia de Deprecación Gradual**: Durante el periodo de transición, el catálogo debe exponer ambos campos (`price_per_hour` y `hourly_rate`) hasta que todos los consumidores migren.
  3. **Pruebas de Contrato Automatizadas**: Incorporar herramientas como **Pact** o esquemas OpenAPI compartidos en el pipeline de CI/CD para bloquear despliegues que rompan compatibilidad.
  4. **Tolerancia en Consumidores (Postel's Law)**: Diseñar el consumidor con esquemas Pydantic que soporten alias o campos opcionales (`hourly_rate: Optional[float] = None`, `price_per_hour: Optional[float] = None`) para adaptarse a variaciones menores sin fallar catastróficamente.

---

## Conclusiones y Buenas Prácticas
1. **Timeouts y Circuit Breakers**: Siempre configurar timeouts estrictos en llamadas inter-servicio y considerar patrones como Circuit Breaker para evitar saturación de hilos.
2. **Health Checks y Observabilidad**: Implementar monitoreo sintético y trazabilidad distribuida (OpenTelemetry / Jaeger) para correlacionar llamadas entre servicios.
3. **Contratos Inmutables**: Tratar los contratos de API pública e interna como inmutables a menos que se incremente la versión principal del servicio.
