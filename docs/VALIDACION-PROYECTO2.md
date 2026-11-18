# Validacion de la rubrica de Proyecto 2

La rubrica completa no se encuentra en el repositorio. Esta matriz corresponde a los requisitos proporcionados y no certifica requisitos adicionales del curso.

| Requisito | Implementacion / comprobacion | Estado |
|---|---|---|
| Recomendaciones y comparacion libro/pelicula | GroqAgent, seis herramientas MCP, fuentes y tests existentes | Requiere prueba con credenciales reales |
| LLM01 directo e indirecto | tests/test_security.py; security/promptfooconfig.yaml | Casos deterministas; evaluación real directa/indirecta pendiente |
| LLM07 | DLP en texto, metadatos y argumentos; pruebas literales/codificadas | Casos deterministas; no certifica ausencia de filtraciones |
| HLD y LLD | PROYECTO2-ARQUITECTURA.md | Documentado |
| Cobertura backend >=80% | pytest --cov=app --cov-fail-under=80 | Ejecutado: ver registro inferior |
| Cobertura frontend >=80% independiente | npm run test:coverage | Ejecutado: ver registro inferior |
| GitHub Flow | CONTRIBUTING, plantilla PR y CI | Revisar PR, revision y proteccion de main en GitHub |
| TMDB | TmdbAttribution y tmdb-logo.ts | Logo y aviso presentes; comprobar visibilidad E2E |
| Widget | Markdown sanitizado, tarjetas, errores, reintento, avatar y movimiento reducido | Suites unitarias y Playwright existentes |
| Docker HTTP y WebSocket | e2e/protocols.spec.ts contra servicios reales | 11 E2E aprobados con MockAgent |

No confundir configuracion de CI con una ejecucion exitosa. El umbral del frontend se aplica por separado a lineas, funciones, ramas y sentencias. Backend configura 80% de cobertura de lineas.

## Comandos de validacion

```bash
npm ci
npm run lint
npm run typecheck
npm run test:coverage
npm run build
cd apps/api
pip install -e ".[dev]"
ruff check .
ruff format --check .
mypy app
pytest --cov=app --cov-fail-under=80
```

Para E2E reproducible sin costo de proveedores, copiar apps/api/.env.example a apps/api/.env sin claves y ejecutar:

```bash
docker compose -f docker-compose.yml -f docker-compose.mock.yml up --build -d
npx playwright install chromium
npm run e2e
docker compose -f docker-compose.yml -f docker-compose.mock.yml down
```

Esto valida integracion web/API y ambos protocolos con MockAgent. Para confirmar Groq + MCP + proveedores reales, quitar el override mock y configurar las claves; ejecutar el test de protocolos y consultas de recomendacion/comparacion manuales. Los tests visuales existentes que esperan respuestas mock no son una suite del modelo real.

El test de protocolos realiza una llamada HTTP y una conexion WebSocket real desde el navegador, verifica los tres eventos y la continuidad de la conversacion. E2E_BASE_URL y E2E_API_URL permiten puertos alternativos. La demo usa HTTP por defecto; la prueba WebSocket valida el contrato del servidor, no el widget completo usando ese transporte.

La atribucion usa el aviso y logo de TMDB; [requisitos oficiales](https://developer.themoviedb.org/docs/faq). Verificar tambien el logo visible y la prominencia relativa al producto en la pantalla final.

## Registro de ejecucion local: 2026-11-17

Base revisada: Proyecto-2, commit 242ddf6. Resultados sobre los cambios de esta entrega:

| Verificacion | Resultado |
|---|---|
| Frontend lint y typecheck | Aprobados |
| Frontend Vitest | 149 pruebas aprobadas |
| Frontend cobertura | Lineas 99.41%, sentencias 98.57%, funciones 99.09%, ramas 96.14% |
| Next.js build | Aprobado |
| Backend Ruff lint/formato y mypy | Aprobados |
| Backend pytest completo | 261 aprobadas, 4 omitidas; 96.17% cobertura |
| Seguridad determinista | 21 aprobadas; security.py 100% cobertura de lineas |
| Docker Compose build/up | Servicios api y web iniciados correctamente |
| Chromium E2E contra Docker | 11 aprobadas: widget, errores/reintento, avatar, movimiento reducido, tarjetas, referencias, logo TMDB y protocolos HTTP/WS |
| Groq real / evaluacion Promptfoo de resistencia | No ejecutada en aquella validación; configuración vigente no inspeccionada |
| Protecciones de rama y revision PR | No verificadas en GitHub; los archivos de CI y CONTRIBUTING no prueban su aplicacion |

Backend se ejecuto en Python 3.12 dentro de Docker, montando el repositorio completo en /workspace y usando /workspace/apps/api como directorio de trabajo. Esto es necesario porque test_compose_config.py lee archivos de la raiz. Las cuatro omisiones corresponden a resolucion dinamica de Compose: la imagen de api no incluye Docker CLI. Los tests estaticos de configuracion si pasaron. No se excluyeron modulos de cobertura para alcanzar el umbral; app/mcp_server.py aparece sin cobertura en el proceso padre porque las pruebas MCP usan un subproceso.

Se agrego un job docker-e2e de CI que conserva evidencias de navegador y limpia servicios al terminar. La ejecucion remota de ese job queda pendiente del push y de GitHub Actions. El Dockerfile web se alinea con Node 24 y usa npm ci para respetar package-lock.json.

La configuracion final Node 24 + npm ci se reconstruyo y paso nuevamente las 11 E2E (19.4 segundos, dos workers). Tras agregar la barrera de argumentos MCP, la suite backend completa volvio a pasar: 261 aprobadas, cuatro omitidas y cobertura 96.17%.

Control negativo de Promptfoo 0.120.0, evaluacion eval-Pd7-2026-11-18T03:36:14: ocho casos ejecutados contra MockAgent por HTTP, cero aprobados, ocho rechazados y cero errores de ejecucion. Es el resultado esperado: la asercion MockAgent evita presentar respuestas simuladas como evidencia de resistencia del modelo real. El codigo de salida no cero es esperado en este control; no debe convertirse en un check de aprobacion de Groq. El archivo local completo esta en security/results/mock-negative-control.json (ignorado por Git). El primer intento de instalacion encontro ECONNRESET; el reintento permitio completar la evaluacion.

## Revisión de evidencia OWASP: 2026-11-18

La referencia anterior es un registro histórico, no una evaluación reproducida
en esta auditoría. En esta copia no están security/results, .promptfoo ni el
ejecutable local de Promptfoo. No se localizaron resultados contra Groq real.
Las pruebas Node del proveedor/assertions no equivalen a ejecutar ese motor.

Base auditada: Proyecto-2, bca0a0d; resultados con las correcciones de esta revisión:

| Comprobación sin APIs reales | Resultado local |
|---|---|
| Seguridad determinista Python | 28 aprobadas (21 existentes + 7 regresiones/controles) |
| Suite backend completa | 291 aprobadas; cobertura 96.42% |
| Ruff, formato y mypy | Aprobados |
| Proveedor y grader de evaluación, Node | 20 aprobadas, fetch simulado |
| Markdown, metadatos y referencias del widget | 71 aprobadas, Vitest con mocks |
| YAML Promptfoo/CI | Parseado: 8 casos, aserción externa, concurrencia 1, demora 65000 ms |
| Motor Promptfoo / modelo Groq | No ejecutados en esta auditoría |

Python local 3.14.5; no se repitió Docker. Antes de la corrección, seis regresiones
de metadatos fallaban: opiniones, overviews y descripciones podían atravesar la
DLP y persistirse aunque el texto principal fuera seguro. Se extendió la revisión
a esos datos antes del commit de memoria. También se reprodujo el falso pase de
un aviso local de presupuesto en el evaluador y se corrigió su clasificación.
El benchmark que usaba la clave sintética `test` se cambió a una clave ficticia
inequívoca para no coincidir con el póster de fixture `test.jpg`; no se debilitó
la protección para hacer pasar esa prueba.

No se declara cumplimiento completo. Falta contrastar la rúbrica íntegra y aportar:

- Evaluación Groq real directa para LLM01 y LLM07, con commit, modelo, parámetros,
  repeticiones, denominadores y errores operativos separados de pases/fallos.
- Evaluación indirecta real con resultados MCP adversariales controlados; la suite
  HTTP actual no inyecta datos en TMDB/Books ni controla sus respuestas.
- Revisión humana de paráfrasis, filtración fragmentada/multiturno, utilidad del
  control benigno y falsos positivos. Los filtros son parciales y no garantizan
  inmunidad frente a prompt injection.
- Artefactos privados verificables y un resumen redactado que pueda presentarse.

Los comandos para una primera muestra de cuatro casos, con espera entre casos,
están en [SEGURIDAD.md](SEGURIDAD.md). No se han hecho llamadas reales ni se han
consultado archivos `.env` durante esta revisión.
