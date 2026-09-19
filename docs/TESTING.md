# Testing

## Filosofía

Tests primero: para cualquier cambio de comportamiento, se escribe (o actualiza) el test antes que la implementación, se corre y se confirma que falla por la razón esperada, y luego se implementa el cambio mínimo para que pase.

Cobertura mínima exigida por la CI: **80% en frontend y 80% en backend, de forma independiente** (no un promedio global).

## Backend (`apps/api`)

Stack: `pytest`, `pytest-asyncio`, `pytest-cov`, `httpx` (cliente ASGI para las rutas REST), `TestClient` de FastAPI/Starlette (para WebSocket).

```bash
cd apps/api
pip install -e ".[dev]"
pytest                                          # tests
pytest --cov=app --cov-report=term-missing      # con cobertura
pytest --cov=app --cov-fail-under=80            # falla si baja de 80%
```

Estructura de `apps/api/tests/`:

- `test_schemas.py` — validación de contratos Pydantic.
- `test_mock_agent.py` — comportamiento del `MockAgent` (protocolo, delay, markdown, errores).
- `test_chat_service.py` — `ChatService` con un agente doble (stub), sin FastAPI.
- `test_health.py`, `test_chat_route.py` — endpoints REST vía `httpx.AsyncClient` + `ASGITransport`.
- `test_websocket.py` — protocolo de eventos del WebSocket vía `TestClient.websocket_connect`.
- `test_deps.py`, `test_config.py` — wiring de dependencias y configuración.

`app.dependency_overrides` se usa para inyectar un `MockAgent(delay_seconds=0)` en los tests (evita pagar la latencia simulada) y para forzar fallos del agente sin acoplar los tests a su implementación real.

## Frontend (`packages/chat-widget`)

Stack: `vitest` (entorno `jsdom`), `@testing-library/react`, `@testing-library/user-event`.

```bash
npm run test --workspace @agichat/chat-widget
npm run test:coverage --workspace @agichat/chat-widget
```

Estructura de `packages/chat-widget/tests/`:

- `http-transport.test.ts` — mockea `fetch` global; cubre request correcto, mapeo de respuesta, timeout (AbortController), error de red, HTTP no-ok, y respuesta con forma inválida.
- `websocket-transport.test.ts` — inyecta un `WebSocketLike` falso (sin abrir sockets reales); cubre conexión perezosa, reutilización de la conexión, typing state, error del servidor y cierre a mitad de flujo.
- `MarkdownRenderer.test.tsx` — headings, bold, italic, listas, links, código inline, bloques de código, y que HTML/scripts embebidos no se ejecuten.
- `ChatComposer.test.tsx` — no envía vacíos, Enter envía, Shift+Enter inserta salto de línea, estado disabled.
- `MessageList.test.tsx` — orden cronológico, diferenciación usuario/agente, typing indicator.
- `useChat.test.ts` — máquina de estados (`idle` → `sending`/`receiving` → `idle`/`error`), reintento sin duplicar el mensaje del usuario, mensajes de error seguros.
- `ChatWidget.test.tsx`, `ChatHeader.test.tsx` — integración de configuración (agentName, welcomeMessage, placeholder, avatar) con un transport inyectado (nunca red real).

El backend real de FastAPI **nunca** se levanta en los tests del frontend: todo transport se testea con dobles (`fetch` mockeado o un `WebSocketLike` falso), por diseño de `ChatTransport`.

## End-to-end (`e2e/`, Playwright)

```bash
npx playwright install --with-deps chromium
npm run e2e
```

Requiere que `apps/web` (con `NEXT_PUBLIC_API_URL` apuntando a un backend real) y `apps/api` estén corriendo — ya sea vía `docker compose up` o localmente.

- **Camino feliz** (`chat.spec.ts`): abre la app, envía un mensaje, verifica que aparece en el historial y que la respuesta del `MockAgent` se renderiza como Markdown.
- **Camino de error**: intercepta la primera llamada a `/api/v1/chat` para forzar un `500`, verifica que se muestra un mensaje de error amigable con botón "Reintentar", y que el reintento (sin interceptar) se recupera.

## Qué NO testear con dobles

- Los contratos Pydantic y TypeScript se testean directamente (sin mocks): son la fuente de verdad del dominio.
- La sanitización de Markdown se testea con contenido real potencialmente inseguro (`<script>`, `onerror`), verificando el DOM resultante — no se mockea `rehype-sanitize`.
