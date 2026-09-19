# API — AGIChat Backend

Base URL: `http://localhost:8000` (configurable vía `NEXT_PUBLIC_API_URL` en el frontend).

Todos los endpoints REST están versionados bajo `/api/v1`.

## `GET /api/v1/health`

Chequeo de salud del servicio.

**Response `200`**

```json
{ "status": "ok" }
```

## `POST /api/v1/chat`

Envía un mensaje del usuario y recibe la respuesta del agente configurado (`MockAgent` en Proyecto 1).

**Request**

```json
{
  "conversation_id": "uuid-o-string-cualquiera",
  "message": { "role": "user", "content": "Hola" }
}
```

**Response `200`**

```json
{
  "conversation_id": "uuid-o-string-cualquiera",
  "message": {
    "id": "uuid",
    "role": "assistant",
    "content": "¡Hola! Soy tu asistente virtual. ¿En qué puedo ayudarte hoy?",
    "created_at": "2026-01-01T00:00:00Z"
  }
}
```

**Errores**

| Status | Causa |
|---|---|
| `422` | `conversation_id` o `message` faltantes, `content` vacío, `role` inválido |
| `502` | El agente falló al generar una respuesta (mensaje genérico, sin detalle interno) |

## `WS /ws/chat`

Protocolo de eventos para simular streaming/latencia del agente.

**Cliente → servidor** (por cada turno):

```json
{ "conversation_id": "conv-1", "content": "Hola" }
```

**Servidor → cliente** (en orden):

```json
{ "type": "agent_start" }
```

```json
{
  "type": "agent_message",
  "conversation_id": "conv-1",
  "message": { "id": "...", "role": "assistant", "content": "...", "created_at": "..." }
}
```

```json
{ "type": "agent_end" }
```

En caso de error, en vez de `agent_message` se envía:

```json
{ "type": "error", "detail": "No pudimos enviar tu mensaje. Intenta nuevamente." }
```

La conexión se mantiene abierta para múltiples turnos; el cliente puede enviar otro mensaje después de recibir `agent_end`.
