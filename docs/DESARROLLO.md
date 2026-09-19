# Guía de desarrollo

## Requisitos

- Node.js 20+
- Python 3.12+
- Docker + Docker Compose (opcional pero recomendado)

## Con Docker (recomendado — hot reload en ambos servicios)

```bash
cp .env.example .env   # opcional, docker-compose ya trae defaults razonables
docker compose up
```

- Frontend: http://localhost:3000
- Backend: http://localhost:8000 (docs interactivas en `/docs`)

Si el puerto 3000 u 8000 ya están en uso en tu máquina, sobreescríbelos sin tocar `docker-compose.yml`:

```bash
WEB_PORT=3001 API_PORT=8001 docker compose up
```

El código de `apps/api` y de todo el repo (`apps/web`, `packages/chat-widget`) se monta como volumen — los cambios se reflejan sin reconstruir la imagen:

- `apps/api`: `uvicorn --reload` detecta cambios en `.py` automáticamente.
- `apps/web`: `next dev` con `WATCHPACK_POLLING=true` (necesario para que el file-watcher funcione de forma confiable sobre volúmenes montados en Docker Desktop).

## Sin Docker

### Backend

```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate   # .venv\Scripts\activate en Windows
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

### Frontend

Desde la raíz del repo (workspaces de npm):

```bash
npm install
npm run dev:web
```

## Variables de entorno

Ver `.env.example`. El frontend solo lee variables `NEXT_PUBLIC_*` (se inyectan en el bundle del cliente). El backend lee `APP_ENV`, `CORS_ORIGINS` y `MOCK_AGENT_DELAY_SECONDS` vía `pydantic-settings`.

## Quality gates antes de un PR

```bash
# Frontend
npm run lint
npm run typecheck
npm run test:coverage --workspace @agichat/chat-widget
npm run build

# Backend (desde apps/api, con el venv activo)
ruff check .
ruff format --check .
mypy app
pytest --cov=app --cov-fail-under=80
```

## Convención de branches

```text
feature/*   fix/*   docs/*   test/*   refactor/*   chore/*
```

Flujo (GitHub Flow): crear branch → desarrollar → tests locales → push → Pull Request → CI → code review → merge a `main`. `main` permanece siempre estable y protegida (PR obligatorio, checks de CI obligatorios).
