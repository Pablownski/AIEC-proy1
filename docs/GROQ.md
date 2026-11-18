# Agente de películas y libros — Bloque 1

Widget → FastAPI → ChatService → GroqAgent → GroqClient → GroqCloud.
GroqAgent descubre y ejecuta herramientas mediante `ClientSession` del SDK MCP
oficial. FastMCP sirve JSON-RPC/STDIO y consulta TMDB/Google Books con httpx.
La dependencia MCP se limita a la línea compatible 1.x (`<2`).

## Configuración y ejecución

Configurar **solo** `apps/api/.env`, usando `apps/api/.env.example` como plantilla:

| Variable | Uso |
|---|---|
| `AGENT_PROVIDER` | Valor explícito del archivo local: `groq` o `mock` |
| `GROQ_API_KEY` | Obligatoria para `groq`; protegida con SecretStr |
| `GROQ_MODEL` | `openai/gpt-oss-120b` por defecto |
| `TMDB_API_KEY` | Clave API v3 de TMDB, no token Bearer |
| `GOOGLE_BOOKS_API_KEY` | Opcional; puede exigirse según cuotas/configuración |

Desde la raíz, con `AGENT_PROVIDER=groq` en **apps/api/.env**:

```powershell
docker compose up --build -d
```

El servicio `api` declara `env_file: ./apps/api/.env`; el proveedor y las claves
se inyectan únicamente en su contenedor. Una variable `AGENT_PROVIDER` heredada
de PowerShell/bash ya no se interpola ni cambia el proveedor. El archivo es
obligatorio: Compose falla claramente si no existe, sin elegir mock silenciosamente.
`CORS_ORIGINS` se calcula en Compose según `WEB_PORT` para la demo local; el resto
de configuración del backend procede del archivo o de los defaults de Settings.
El frontend no monta el backend, no recibe claves y los secretos se excluyen del build.
Sin Docker, Pydantic mantiene su precedencia habitual de entorno sobre `.env`.

Para activar MockAgent deliberadamente en todo el stack, sin editar credenciales:

```powershell
docker compose -f docker-compose.yml -f docker-compose.mock.yml up --build -d
```

El override fija `mock` explícitamente y no se carga por defecto. Para volver a la
configuración local usar `docker compose up --build -d`. Otra opción deliberada
es editar solo `AGENT_PROVIDER=mock` en el archivo local. Los cambios de entorno
requieren recreación mediante `up`; `restart` no recarga `env_file`.
Una prueba aislada puede usar `docker compose run --rm --no-deps -e AGENT_PROVIDER=mock api pytest`.

Verificar únicamente el proveedor y la clase, sin volcar variables ni secretos:

```powershell
docker compose exec -T api python -c "from app.core.config import get_settings; from app.api.deps import get_chat_service; print(get_settings().agent_provider, type(get_chat_service().agent).__name__)"
```

La salida esperada en modo real es `groq GroqAgent`; en modo simulado, `mock MockAgent`.
La comprobación no llama a Groq, TMDB ni Books. No compartir `docker compose config`,
`docker inspect`, `env` o dumps de Settings: pueden incluir claves. La selección
del agente sigue en `api/deps.py`, sin cambios de lógica.

## MCP y metadatos

Ejecutar por separado desde `apps/api`: `python -m app.mcp_server`.
Este proceso solo recibe variables de entorno; no carga `.env`. Un cliente MCP
externo debe pasar las claves del catálogo en su configuración de entorno.
STDOUT se reserva al protocolo. No se pasan credenciales Groq al proceso MCP.

Se exponen `search_movies(query, year?)`, `discover_movies(genre, min_rating?)`,
`movie_details(movie_id)`, `search_books(title?, author?)` y `book_details(volume_id)`.
El descubrimiento publica esquemas JSON de entrada y salida. Se validan en ambos
extremos. El agente no llama directamente a funciones de catálogo. Cada turno
abre un proceso del mismo intérprete y lo cierra mediante los context managers
oficiales, incluso ante errores. No hay puertos MCP ni infraestructura adicional.

`Movie`, `Book` y `ToolResult` conservan IDs, fuentes, pósteres, IMDb, créditos y
datos bibliográficos. Los resultados tipados quedan como artefactos de memoria,
independientes del texto del LLM, para una futura extensión del servicio. Los
contratos HTTP/WS actuales siguen devolviendo texto; no hay tarjetas ni acciones.

## Límites y memoria

Hasta 8 llamadas a herramientas y 9 rondas LLM por turno: una por herramienta
secuencial más una respuesta final. Al agotarse herramientas o rondas, se solicita
síntesis con `tool_choice=none`; no se permiten consultas adicionales. Cinco
rondas no bastaban para investigar tres películas, buscar tres libros y consultar
un volumen (7 herramientas + respuesta final). El límite total sigue siendo 60 s.
Se deshabilita `parallel_tool_calls`: GPT OSS soporta herramientas,
pero no parallel tool use según la documentación consultada. Alternativa
configurable: `GROQ_MODEL=openai/gpt-oss-20b`. No hay fallback silencioso ni
activación de facturación; verificar disponibilidad y cuotas Free en la cuenta.

Timeouts: Groq E/S 10 s (sin reintentos del SDK), catálogos 5 s, llamada MCP 8 s, turno 60 s,
HTTP del widget 75 s. Máximo 8 turnos simultáneos y 10 solicitudes/minuto por
conversación. Entrada hasta 4000 caracteres, conversation_id hasta 128, consultas
hasta 5 resultados. No hay navegación libre, escritura ni comandos del modelo.
Hosts/rutas son fijos y enlaces se construyen con identificadores validados.
Los errores no incluyen cuerpos ni credenciales. No activar logs detallados del SDK/httpx.

La memoria conserva hasta 6 turnos completos, 24000 caracteres serializados,
12 resultados tipados y 128 conversaciones, con TTL inactivo de 15 minutos.
Los turnos guardan diálogo, sin repetir trazas MCP. Una caché adicional de hasta
12 consultas exitosas por conversación reutiliza argumentos normalizados; nunca
comparte datos entre conversaciones ni confirma trabajo de un turno fallido.
Se serializan turnos por conversación; solo se confirman al terminar correctamente,
incluido el cierre MCP. Una respuesta parcial tras un error de herramienta/API
no actualiza historial, artefactos ni la respuesta usada para deduplicación.
Texto idéntico al último turno exitoso reutiliza su respuesta: el contrato actual
no proporciona ID de solicitud para deduplicación exacta. Un turno demasiado grande
se descarta entero del historial. Se pierde memoria al reiniciar; usar **un worker**
para la demo. No hay sincronización entre réplicas. El ID no sustituye autenticación:
quien conoce un ID puede reutilizarlo.

## Evidencia, pruebas y pendientes

El prompt exige distinguir hechos, inferencias y datos ausentes; ofrece comparación
libro/película y prohíbe inventar diferencias. Keywords y créditos con nombre/rol
aportan evidencia, pero títulos similares no confirman relación. Sin evidencia
específica, debe declararse que no puede confirmarse. Las APIs no son exhaustivas;
algunas relaciones no podrán resolverse. Valorar si merece verse es una recomendación
subjetiva limitada a los metadatos disponibles.

Los resultados externos son datos no confiables. Prompt y validación no garantizan
ausencia de prompt injection o alucinaciones. LLM01/LLM07 quedan para otro bloque.
Desde `apps/api`: `ruff check .`, `ruff format --check .`, `mypy app` y
`pytest --cov=app --cov-fail-under=80`. Las pruebas bloquean HTTP externo y lectura
de `.env`; prueban MCP real con APIs simuladas y HTTP/WS con Groq simulado.
La cobertura principal no incluye líneas ejecutadas en subprocess.
Pendiente smoke test con credenciales, Docker disponible, cuotas, latencia y
calidad semántica del modelo real. No se hacen llamadas reales durante pruebas.

## Diagnóstico seguro

El logger `uvicorn.error` emite eventos JSON `agent_tool_finished`,
`agent_tool_failed`, `agent_turn_failed` y `agent_turn_completed`. Incluyen un
`run_id` aleatorio por ejecución, etapa, rondas, herramientas ejecutadas, tiempo,
código controlado y `memory_committed`; errores HTTP de Groq añaden solo el status
numérico. No incluyen conversation_id, mensajes, argumentos, resultados, claves,
system prompt, cuerpos de excepciones ni tracebacks. Los nombres de herramienta
desconocidos se registran como `unknown`. Fallos de catálogo se distinguen por
`catalog_authentication`, `catalog_rate_limit`, `catalog_timeout`, etc.; fallos
Groq por `groq_*`. Revisar el código/etapa aunque el access log muestre HTTP 200:
se conserva el contrato que devuelve un mensaje seguro como respuesta de chat.

La regresión simulada demuestra insuficiencia de rondas, no la causa histórica
exacta del incidente sin diagnósticos. No confirma fallos reales de Google Books,
credenciales, cuotas, memoria o Groq. Los nuevos eventos permiten distinguirlos
en futuras ejecuciones sin registrar contenido sensible.

El mensaje genérico se produce al capturar excepciones de memoria (capacidad o
frecuencia), timeout del turno, conexión/descubrimiento/cierre MCP, errores Groq,
respuesta vacía/excesiva o presupuestos agotados. Un error de Google Books por sí
solo devuelve un `ToolResult.error`; no dispara directamente ese mensaje. Antes
podía provocar más consultas hasta agotar rondas, sin que se registrase la causa.
Los errores de ejecución de herramientas también se comunican al modelo de forma
segura, pero ahora impiden confirmar el turno en memoria aunque haya texto final.

## Tokens y HTTP 429

El LLM recibe evidencias consolidadas por tipo/ID una sola vez, más el último
intercambio de herramientas (referencias a esas evidencias). Se omiten pósteres e
IMDb del contexto, pero se conservan completos en backend. Sinopsis/descripciones
se limitan a 350 caracteres con `truncated_fields`; cuando hay referencias a
adaptaciones después del prefijo, se incluye un extracto de esa zona. Identidades,
autores, fechas, créditos, keywords, calificaciones e identificadores no se resumen.
Se conserva completo el último diálogo para resolver referencias a las tres
películas; los anteriores se abrevian a 1000 caracteres por mensaje. Los esquemas
eliminan títulos decorativos sin alterar parámetros. GPT OSS usa `reasoning_effort=low`
con el mismo máximo de salida (1800); otros modelos omiten ese parámetro.

Hay **un reintento total por turno**, compartido entre rondas. Solo para señales
TPM/RPM explícitas, con `retry-after` válido (segundos o fecha HTTP) y tiempo
restante suficiente para esperar más el timeout de E/S. No hay un corte fijo de
8 s: una espera de 12 s puede recuperarse si cabe en el presupuesto de 60 s.
No se adelanta una espera que no cabe: se devuelve un mensaje comprensible.
Cuotas diarias RPD/TPD/daily y tipos
desconocidos no se reintentan; tampoco cabeceras ausentes/inválidas. El SDK sigue
con `max_retries=0`. Hasta 9 rondas lógicas implican como máximo 10 peticiones HTTP
incluyendo ese único reintento, dentro de los 60 s totales (widget: 75 s).

`groq_rate_limited` registra tipo controlado, demora y decisión de reintento;
`groq_usage` registra conteos reales de tokens cuando el SDK los proporciona.
Se incluyen tamaños en caracteres de mensajes/esquemas, nunca su contenido.
Según Groq, `remaining-requests` corresponde a RPD y `remaining-tokens` a TPM.
No se puede identificar la cuota del incidente histórico sin señales adicionales.
Los límites son de organización; otras sesiones pueden consumir la misma cuota.
No hay contador distribuido ni garantía de completar toda comparación en Free.
Los resúmenes y razonamiento bajo requieren verificar calidad con el modelo real.

Referencias: [límites y cabeceras Groq](https://console.groq.com/docs/rate-limits),
[razonamiento GPT OSS](https://console.groq.com/docs/reasoning).

## Cuota de Google Books

El primer `rate_limit` de `search_books` o `book_details` termina el turno con una
explicación determinista de que la comparación no puede verificarse. No se
ejecutan herramientas restantes del lote, variantes de búsqueda ni más rondas
Groq para insistir sobre la fuente indisponible. No se guarda ese turno, ni sus
artefactos/caché parciales. La memoria previa permanece y una petición manual
posterior puede volver a usar Books; no hay bloqueo persistente entre turnos.

Antes, `catalog_rate_limit` solo podía provenir de un HTTP 429. Ahora también se
reconoce un 403 de Books con razón estructurada de cuota conocida. Otros 401/403
siguen como autenticación, 5xx como indisponibilidad, y timeouts/conexión conservan
sus códigos propios. No se interpreta texto libre de errores para clasificarlos.

`catalog_request_failed` incluye fuente, operación permitida, código, status HTTP
y razón del proveedor de una lista cerrada (`rateLimitExceeded`,
`dailyLimitExceeded`, etc.; el resto se registra como `unknown`). No incluye URL,
parámetros, cuerpos ni mensajes del proveedor. El logger propio mantiene avisos
visibles en el subprocess MCP; se suprimen registros INFO/DEBUG de httpx porque
sus URLs pueden contener claves y búsquedas. No reactivar esos logs con secretos.
Estos datos permiten investigar el incidente, pero no demuestran retrospectivamente
qué cuota o configuración concreta de Google causó los 429.

Las pruebas del agente bloquean conexiones MCP no simuladas por defecto: los
mocks HTTP del proceso padre no protegen por sí solos a un subprocess. Las pruebas
MCP explícitas existentes mantienen su transporte real con servicios simulados.

Referencias: [Groq](https://console.groq.com/docs/tool-use/overview),
[MCP](https://github.com/modelcontextprotocol/python-sdk/tree/v1.x),
[TMDB](https://developer.themoviedb.org/reference/movie-details),
[Google Books](https://developers.google.com/books/docs/v1/using).

La corrección preventiva y las mediciones reproducibles están en
[EFICIENCIA_GROQ.md](EFICIENCIA_GROQ.md).

## Diagnóstico de HTTP 400 después de MCP

Los mensajes de respuesta del SDK conservan campos adicionales del proveedor.
El filtro anterior de `model_dump(include=...)` solo limitaba el nivel superior:
podía reenviar `tool_calls[].index` o atributos adicionales de `function`, que no
pertenecen al contrato de solicitud. Esa serialización ya existía antes de
`82d1ea7`; no demuestra una regresión introducida por la optimización o el avatar.

Ahora el mensaje assistant se construye explícitamente: role, content opcional y
tool_calls con id, type y function(name, arguments). Se excluyen extras y campos
de razonamiento. IDs vacíos o duplicados abortan antes de ejecutar MCP; cada
resultado conserva su ID, orden y contenido string.

`test_groq_wire_contract.py` usa el SDK Groq real y HTTP simulado con validación
estricta. Antes del cambio rechazaba la segunda solicitud con 400 después de un
`discover_movies` exitoso; con el cambio acepta el mismo escenario, también con
varias herramientas. `compare_movies` sigue sintetizando sin esquemas ni trazas
de herramientas. No se añaden rondas, reintentos ni tokens de contexto.

En la ronda posterior a discovery se conserva tool_choice auto; la síntesis sin
esquemas omite tool_choice (su valor predeterminado es none). reasoning_effort low
es válido para GPT-OSS 120b. No se identificó incompatibilidad en esos parámetros.
Referencias: [contrato Groq](https://console.groq.com/docs/api-reference),
[herramientas locales](https://console.groq.com/docs/tool-use/local-tool-calling).

Un HTTP 400 también puede indicar un fallo de generación del modelo, no solo una
solicitud mal formada. El nuevo evento `groq_request_failed` registra run_id,
status, clasificación, código/tipo permitidos, categoría de parámetro/campo,
presencia booleana de failed_generation, conteos y opciones de solicitud.
`tool_use_failed` se clasifica como tool_generation; códigos desconocidos de 400
permanecen bad_request_unknown. Nunca se registran cuerpos, prompts, resultados,
valores de failed_generation, claves ni cabeceras. No se reintenta ningún 400.

**La causa del incidente real sigue pendiente:** sus logs anteriores no incluyen
el motivo del proveedor. El defecto de serialización está demostrado con mocks,
pero no prueba que el incidente contuviera index. Tras desplegar el cambio, una
única repetición manual de la consulta y el evento correlacionado por run_id
permitirán verificarlo o identificar otra causa sin exponer contenido sensible.
