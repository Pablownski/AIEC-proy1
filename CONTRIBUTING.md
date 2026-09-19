# Contribuir a AGIChat

## Flujo (GitHub Flow)

1. Crear una branch desde `main` siguiendo la convención `feature/*`, `fix/*`, `docs/*`, `test/*`, `refactor/*` o `chore/*`.
2. Desarrollar siguiendo **tests primero**: escribir/actualizar el test, verlo fallar, implementar el cambio mínimo, verlo pasar.
3. Correr los quality gates locales (ver [docs/DESARROLLO.md](docs/DESARROLLO.md)).
4. Abrir un Pull Request contra `main` usando la plantilla (`.github/pull_request_template.md`).
5. Esperar a que la CI pase y a que al menos una persona del equipo revise el PR.
6. Mergear a `main` — `main` debe permanecer siempre estable.

## Antes de abrir un PR

- [ ] Tests agregados o actualizados para el comportamiento nuevo/cambiado.
- [ ] `npm run lint` y `npm run typecheck` pasan (frontend).
- [ ] `ruff check .`, `ruff format --check .` y `mypy app` pasan (backend).
- [ ] Cobertura ≥ 80% en frontend y backend.
- [ ] `npm run build` pasa.
- [ ] Documentación actualizada si el comportamiento o la arquitectura cambiaron.
- [ ] Ningún secreto commiteado (revisar `git diff` antes de hacer push).

## Reglas de arquitectura

Ver [AGENTS.md](AGENTS.md) — aplica tanto a contribuciones humanas como a cambios hechos por herramientas agénticas (Claude Code, Codex, etc.).

## Estilo de commits

Mensajes cortos en imperativo, con prefijo por tipo cuando ayude a la claridad: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`.
