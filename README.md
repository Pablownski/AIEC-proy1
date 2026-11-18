# AGIChat SDK

Widget de chat reutilizable (`@agichat/chat-widget`) con un backend FastAPI de referencia (GroqAgent y herramientas MCP en Proyecto 2; MockAgent para pruebas). Monorepo con Next.js, FastAPI y un SDK de React desacoplado del backend mediante un contrato de transporte (`ChatTransport`).

Proyecto 2: disponible `GroqAgent` con herramientas MCP reales para TMDB y Google
Books y memoria acotada. El proveedor local se configura en `apps/api/.env` y
`MockAgent` sigue disponible mediante selección explícita. Ver
[configuración y ejecución del agente](docs/GROQ.md).

Bloque 2: tarjetas con pósteres, comparaciones, referencias verificadas y atribución
TMDB. Ver [interfaz, compatibilidad y prueba en navegador](docs/INTERFAZ.md).

## Requisitos

- Docker + Docker Compose (recomendado), **o**
- Node.js 24+ y Python 3.12+ para correr los servicios sin contenedores.

## Puesta en marcha rápida (Docker, con hot reload)

```bash
git clone <este-repositorio>
cd agichat
# Crear apps/api/.env desde apps/api/.env.example si aún no existe y configurarlo.
docker compose up --build -d
```

- Frontend: http://localhost:3000
- Backend: http://localhost:8000 (documentación interactiva en `/docs`)

Compose carga `apps/api/.env` solo en `api`; un `AGENT_PROVIDER` heredado del shell
no sustituye el valor del archivo. Para MockAgent intencional:
`docker compose -f docker-compose.yml -f docker-compose.mock.yml up --build -d`.
Ver [cómo comprobar el proveedor sin secretos](docs/GROQ.md#configuración-y-ejecución).

Si el puerto 3000 u 8000 ya están en uso en tu máquina:

```bash
WEB_PORT=3001 API_PORT=8001 docker compose up
```

Los cambios en el código de `apps/api`, `apps/web` y `packages/chat-widget` se reflejan sin reconstruir la imagen.

## Sin Docker

```bash
# Backend
cd apps/api
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload

# Frontend (en otra terminal, desde la raíz)
npm install
npm run dev:web
```

Ver [docs/DESARROLLO.md](docs/DESARROLLO.md) para más detalle.

## Variables de entorno

Ver [.env.example](.env.example) para puertos/frontend y
[apps/api/.env.example](apps/api/.env.example) para la configuración del backend.
Nunca versionar un `.env` con secretos reales.

## Testing y cobertura

```bash
# Frontend
npm run test:coverage --workspace @agichat/chat-widget

# Backend
cd apps/api && pytest --cov=app --cov-fail-under=80
```

La CI exige ≥80% de cobertura en frontend y backend de forma independiente. Ver [docs/TESTING.md](docs/TESTING.md).

## Lint, typecheck y build

```bash
npm run lint
npm run typecheck
npm run build
```

## Docker

`docker-compose.yml` define dos servicios (`api`, `web`) con volúmenes montados para hot reload — no hace falta reconstruir la imagen durante el desarrollo normal. Reconstruir solo cuando cambian las dependencias:

```bash
docker compose build
```

## Arquitectura

```text
ChatWidget → ChatTransport → FastAPI → ChatService → Agent interface → MockAgent / agente real
```

El frontend nunca depende de una implementación concreta del agente. Ver [docs/ARQUITECTURA.md](docs/ARQUITECTURA.md) para el diagrama completo, la justificación de cada decisión y cómo extender cada capa (nuevos componentes, nuevos transports, un agente real).

## Estructura del repositorio

```text
apps/web/               Next.js — app de demostración que consume el SDK
apps/api/                FastAPI — REST /api/v1, WebSocket /ws/chat, GroqAgent/MCP
packages/chat-widget/    SDK reutilizable (@agichat/chat-widget)
docs/                    Arquitectura, API, desarrollo, testing
e2e/                     Tests end-to-end (Playwright)
```

## GitHub Flow

`main` permanece estable. Todo cambio pasa por un Pull Request con CI obligatoria y revisión de al menos una persona. Ver [CONTRIBUTING.md](CONTRIBUTING.md).

## Documentación para herramientas agénticas

Ver [AGENTS.md](AGENTS.md) — reglas arquitectónicas, comandos y checklist antes de terminar una tarea.

## Proyecto 2: arquitectura, seguridad y validacion

Damian implementa un agente Groq con herramientas MCP para TMDB y Google Books, memoria acotada y tarjetas de fuentes verificadas. La demo utiliza HTTP; el SDK y API tambien soportan WebSocket.

- [HLD, LLD, componentes y escalabilidad](docs/PROYECTO2-ARQUITECTURA.md)
- [OWASP LLM01/LLM07, defensas y evaluaciones Promptfoo](docs/SEGURIDAD.md)
- [Matriz de rubrica y validacion Docker HTTP/WebSocket](docs/VALIDACION-PROYECTO2.md)

La barrera de salida inspecciona texto y metadatos anidados antes de guardar el
turno; también se revisan argumentos de herramientas. Es una defensa parcial.
La auditoría de seguridad del 2026-11-18 no demuestra todavía cumplimiento total
de LLM01/LLM07: faltan resultados verificables contra Groq real y la rúbrica íntegra.
Consultar [evidencia, límites y comandos de evaluación](docs/SEGURIDAD.md).
