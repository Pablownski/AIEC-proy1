# AGIChat SDK

Monorepo bootstrap: Next.js (`apps/web`), FastAPI (`apps/api`) y el SDK de chat (`packages/chat-widget`).

## Correr localmente

### Con Docker

```bash
docker compose up
```

- Frontend: http://localhost:3000
- Backend: http://localhost:8000

### Sin Docker

```bash
# Backend
cd apps/api
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload

# Frontend (desde la raíz)
npm install
npm run dev:web
```

Este README se irá completando a medida que el proyecto avance (arquitectura, testing, contribución).
