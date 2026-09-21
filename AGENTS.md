# AGENTS.md

Guía rápida para Claude, Codex y cualquier herramienta agéntica que trabaje en este repositorio.

## Arquitectura

Monorepo con tres paquetes:

```text
apps/web              Next.js (demo consumidora del SDK)
apps/api              FastAPI + capa agéntica (MockAgent hoy, agente real en Proyecto 2)
packages/chat-widget   SDK de chat reutilizable (@agichat/chat-widget)
```

Dependencia deseada (nunca al revés):

```text
ChatWidget → ChatTransport → FastAPI → ChatService → Agent interface → MockAgent / agente real
```

Ver [docs/ARQUITECTURA.md](docs/ARQUITECTURA.md) para el detalle y el diagrama completo.

## Reglas

- No realizar llamadas HTTP ni abrir WebSockets directamente desde componentes visuales. Todo pasa por `ChatTransport`.
- No introducir lógica agéntica dentro del frontend.
- Los endpoints REST se mantienen bajo `/api/v1`.
- `ChatService` depende de la interfaz `Agent` (Protocol), nunca de `MockAgent` directamente.
- Toda funcionalidad nueva requiere tests. Cobertura mínima: 80% en frontend y backend, verificada de forma independiente (no un promedio global).
- Evitar `any` en TypeScript salvo justificación explícita en comentario.
- No usar `dangerouslySetInnerHTML` para mensajes del agente — `MarkdownRenderer` sanitiza con `rehype-sanitize`.
- Mantener componentes y servicios con responsabilidades pequeñas (ver estructura de `packages/chat-widget/src`).
- No introducir secretos en el repositorio. Usar `.env.example` como referencia, nunca commitear `.env`.

## Comandos

Frontend (desde la raíz, con npm workspaces):

```bash
npm install                                 # requiere Node.js 24+
npm run dev:web                                    # Next.js con hot reload
npm run test --workspace @agichat/chat-widget       # Vitest
npm run test:coverage --workspace @agichat/chat-widget
npm run lint
npm run typecheck
npm run build
```

Backend (desde `apps/api`, con un entorno virtual activado):

```bash
pip install -e ".[dev]"
uvicorn app.main:app --reload                       # hot reload
ruff check .
ruff format --check .
mypy app
pytest --cov=app --cov-fail-under=80
```

Todo el stack con Docker (hot reload en ambos servicios):

```bash
docker compose up
```

## Testing

- Backend: `pytest` + `pytest-asyncio` + `httpx` (ASGI transport) + `pytest-cov`. Ver [docs/TESTING.md](docs/TESTING.md).
- Frontend: Vitest + React Testing Library, entorno `jsdom`. Transports se testean inyectando dobles (`createWebSocket`, `fetch` mockeado) — nunca golpeando la red real.
- E2E: Playwright (`e2e/`), camino feliz y camino de error contra la app real.

## Límites arquitectónicos

- El widget (`packages/chat-widget`) no debe importar nada de `apps/web` ni `apps/api`.
- `ChatTransport` es la única superficie de comunicación del widget con el backend — para agregar un nuevo mecanismo (SSE, gRPC-web, etc.) se implementa la interfaz, no se modifica `ChatWidget`.
- Para reemplazar `MockAgent` por un agente real (Proyecto 2), implementar el `Protocol Agent` en `apps/api/app/agents/` e inyectarlo en `ChatService` vía `app/api/deps.py`. No debería requerir cambios en `ChatService`, en las rutas, ni en el frontend.

## Antes de terminar una tarea

Frontend:

```bash
npm run lint
npm run typecheck
npm run test:coverage --workspace @agichat/chat-widget
npm run build
```

Backend:

```bash
ruff check .
ruff format --check .
mypy app
pytest --cov=app --cov-fail-under=80
```

No considerar una tarea terminada únicamente porque funciona visualmente: los checks anteriores deben pasar y, si el comportamiento cambió, los tests deben actualizarse primero.
