# Agente de películas y libros — Bloque 1

Widget → FastAPI → ChatService → GroqAgent → GroqClient → GroqCloud.
GroqAgent descubre y ejecuta herramientas mediante `ClientSession` del SDK MCP
oficial. FastMCP sirve JSON-RPC/STDIO y consulta TMDB/Google Books con httpx.
La dependencia MCP se limita a la línea compatible 1.x (`<2`).

## Configuración y ejecución

Configurar **solo** `apps/api/.env` con los nombres de `.env.example`:

| Variable | Uso |
|---|---|
| `AGENT_PROVIDER` | `mock` por defecto; `groq` activa el agente real |
| `GROQ_API_KEY` | Obligatoria para `groq`; protegida con SecretStr |
| `GROQ_MODEL` | `openai/gpt-oss-120b` por defecto |
| `TMDB_API_KEY` | Clave API v3 de TMDB, no token Bearer |
| `GOOGLE_BOOKS_API_KEY` | Opcional; puede exigirse según cuotas/configuración |

Desde la raíz, en PowerShell:

```powershell
$env:AGENT_PROVIDER = 'groq'
docker compose up --build
```

En bash: `AGENT_PROVIDER=groq docker compose up --build`.
Compose selecciona el agente desde el shell; el backend lee las claves del
archivo montado en `/app/.env`. El frontend no monta el backend y los secretos se
excluyen del build. Sin Docker, ejecutar Uvicorn desde `apps/api`.

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

Hasta 5 rondas LLM y 8 llamadas por turno, seleccionadas dinámicamente y ejecutadas
en secuencia. Se deshabilita `parallel_tool_calls`: GPT OSS soporta herramientas,
pero no parallel tool use según la documentación consultada. Alternativa
configurable: `GROQ_MODEL=openai/gpt-oss-20b`. No hay fallback silencioso ni
activación de facturación; verificar disponibilidad y cuotas Free en la cuenta.

Timeouts: Groq E/S 10 s sin reintentos, catálogos 5 s, llamada MCP 8 s, turno 60 s,
HTTP del widget 75 s. Máximo 8 turnos simultáneos y 10 solicitudes/minuto por
conversación. Entrada hasta 4000 caracteres, conversation_id hasta 128, consultas
hasta 5 resultados. No hay navegación libre, escritura ni comandos del modelo.
Hosts/rutas son fijos y enlaces se construyen con identificadores validados.
Los errores no incluyen cuerpos ni credenciales. No activar logs detallados del SDK/httpx.

La memoria conserva hasta 6 turnos completos, 24000 caracteres serializados,
12 resultados tipados y 128 conversaciones, con TTL inactivo de 15 minutos.
Se serializan turnos por conversación; solo se confirman al terminar correctamente.
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

Referencias: [Groq](https://console.groq.com/docs/tool-use/overview),
[MCP](https://github.com/modelcontextprotocol/python-sdk/tree/v1.x),
[TMDB](https://developer.themoviedb.org/reference/movie-details),
[Google Books](https://developers.google.com/books/docs/v1/using).
