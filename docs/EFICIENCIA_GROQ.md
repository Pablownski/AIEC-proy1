# Eficiencia y presupuesto de Damián

## Causa y solución

El ciclo anterior ofrecía cinco operaciones granulares y permitía continuar
investigando hasta ocho herramientas. Procesaba múltiples `tool_calls`, pero
secuencialmente. Cada ronda reenviaba esquemas, diálogo y evidencias acumuladas.
Los metadatos visuales se construyen localmente: no necesitan otra consulta LLM.

Groq documenta que **GPT-OSS 120b no admite parallel tool use**:
[tabla oficial](https://console.groq.com/docs/tool-use/overview). Activar esa opción
no resuelve las búsquedas dependientes. Conservamos el modelo y un único agente.

La nueva herramienta MCP real `compare_movies(movie_ids)` acepta hasta tres IDs:
consulta detalles TMDB con concurrencia máxima dos y luego Books por título y,
cuando consta, escritor con rol `Novel`. Books se consulta secuencialmente y se
detiene ante el primer error. Máximo seis consultas HTTP por operación; no es
una sola petición al proveedor. No selecciona arbitrariamente entre libros ni
confirma relaciones por títulos similares. No necesita consultar detalles de un
libro si su búsqueda ya proporciona los datos bibliográficos necesarios.

El LLM decide usar la herramienta. Una comparación con fuentes completas pasa a
síntesis sin esquemas ni trazas de planificación. Fuentes incompletas permiten
consultas dependientes posteriores. La comparación sigue distinguiendo relación
confirmada/no confirmada; no se inventan diferencias de escenas.

Las múltiples llamadas independientes recibidas se ejecutan con concurrencia dos,
manteniendo orden e IDs de los mensajes `tool`. Books y las operaciones compuestas
comparten una exclusión para evitar variantes tras un error de cuota. Se deduplican
solicitudes equivalentes mediante argumentos validados, espacios/case normalizados
en búsquedas e IDs ordenados en comparaciones. La caché sigue aislada por conversación;
una comparación también conserva los resultados individuales para futuras consultas.
Los timeouts son ocho segundos por herramienta simple, 26 por comparación y
60 por turno. Los subprocess MCP mantienen su ciclo de vida y cierre existentes.

El contexto conserva hasta doce mensajes (el último intercambio completo y los
anteriores abreviados a 1000 caracteres, como antes),
evidencias consolidadas sin duplicados y extractos deterministas de hasta 350
caracteres. Se mantienen IDs, títulos, autores, fechas, créditos y fuentes; los
extractos señalan lo truncado. Los artefactos completos permanecen en backend para
pósteres, comparaciones y acciones verificadas del Bloque 2.
Para Books se incluye una descripción por búsqueda: se prioriza coincidencia de
título/autor con TMDB, sin convertir ese orden en prueba de adaptación. Los demás
candidatos conservan su identidad bibliográfica y marcan `omitted_fields`.
Una regresión con quince candidatos y descripciones largas verifica que los datos
completos se conservan y la síntesis cabe en el presupuesto predeterminado.

## Admisión preventiva y cuotas

Variables opcionales exclusivamente backend, documentadas en `apps/api/.env.example`:

- `GROQ_TPM_BUDGET=8000`: referencia ajustable a la cuota real de la organización.
  Se utiliza 90% como margen local; no altera la cuota del proveedor.
- `GROQ_TURN_TOKEN_BUDGET=7000`: presupuesto por turno.

Antes de pedir una respuesta se estima la entrada mediante bytes UTF-8/3 y
sobrecarga por mensaje. Se reservan hasta 1800 tokens de salida (incluido
razonamiento), ajustando `max_completion_tokens` a la capacidad disponible.
Se exige un mínimo de 768; no se envían solicitudes que deliberadamente excedan
el presupuesto estimado. No se aumentaron las cuotas configuradas.
**Es una heurística prudente, no el tokenizer GPT-OSS ni una cota garantizada.**
Cuando existe `usage`, sus contadores reales sustituyen la reserva una sola vez,
sin sumar de nuevo el razonamiento ni la estimación. Sin `usage` se carga una
estimación marcada como tal. No se confunden caracteres y tokens.

El cliente compartido separa uso liquidado, solicitudes en vuelo y reservas de
síntesis, incluidas otras conversaciones del mismo proceso. El uso expira 60 s
después de recibir la respuesta; una petición todavía en vuelo nunca expira por
cumplir 60 s. La admisión/reserva es atómica en el event loop. Se calcula cuándo
expiran suficientes registros, no solo el primero, y se espera únicamente si
caben la espera y el timeout HTTP en los 60 s totales del turno.

Antes de ejecutar MCP se reserva una síntesis mínima, con margen estimado de 600
tokens para evidencia nueva y tiempo para herramienta/LLM. Si se sabe que no cabe,
no se ejecuta la herramienta. La reserva se reutiliza en la siguiente llamada,
no se vuelve a sumar. No garantiza el tamaño de resultados todavía desconocidos.

Si otra ronda de investigación no cabe y hay artefactos, se intenta una síntesis
sin esquemas, con el último intercambio y extractos de 120 caracteres. Se conservan
IDs, títulos, autores, fechas y fuentes; los artefactos visuales permanecen completos.
Una respuesta truncada no se guarda como completa. Si tampoco cabe la síntesis,
se devuelve un mensaje explícito de **presupuesto local**, con segundos de espera
cuando pueden calcularse, y no se guarda el turno fallido.

Todas las reservas se liberan en `finally`, también ante error/cancelación. Un
rechazo local, HTTP de validación/autenticación o 429 no deja una reserva cobrada.
Los tokens confirmados de la primera llamada sí permanecen en la ventana aunque
falle el turno. Cuando una llamada enviada termina con facturación incierta
(timeout, desconexión/cancelación en vuelo, 5xx o fallo de generación sin usage),
se registra por prudencia un consumo estimado durante 60 s, no una reserva huérfana.

Se conserva **un único reintento por turno** exclusivamente para TPM/RPM explícitos,
respetando `retry-after` y la duración restante. Nunca se reintentan automáticamente
límites diarios/desconocidos. El SDK no añade reintentos propios. Un error de cuota
de Books sigue abortando sin guardar turnos, cachés ni metadatos incompletos.

`groq_usage`, `groq_usage_uncertain`, `groq_budget_admitted`, `groq_budget_wait`,
`groq_budget_limited`, `groq_budget_released` y los eventos del agente
permiten correlacionar rondas, uso real, estimación y decisión mediante `run_id`.
Solo registran contadores/códigos: sin conversaciones, argumentos, URLs con claves,
credenciales ni system prompt. Las cuotas son de organización y pueden consumirse
desde otros procesos: este contador local no garantiza evitar todos los 429.
[Referencia de Groq](https://console.groq.com/docs/rate-limits).

### Regresión de bloqueos locales

El cálculo anterior requería siempre entrada estimada + 1800, incluso para una
síntesis corta. Con 2663 tokens ya consumidos y entrada siguiente **simulada** de
3000: `2663 + 3000 + 1800 = 7463 > 7000`, por lo que rechazaba localmente sin 429.
Con 2655 ocurría lo mismo. Esperar entre turnos no corregía ese techo del turno.

Ahora la disponibilidad es el mínimo de lo restante por turno y por minuto,
descontando otras solicitudes/reservas. Sin consumo externo reciente:
`min(7000 - 2663, 7200 - 2663) = 4337`; la salida se limita a `4337 - 3000 = 1337`.
Para 2655, permite 1345. Si el SDK reporta finalmente otros 1000 tokens, el total
cargado es 3663/3655; el sobrante se libera inmediatamente. Los 3000 estimados son
una condición de reproducción, no una medición de los incidentes de producción.

También se corrigió que un HTTP 400 dejara su reserva en el contador, y que la
ventana esperara hasta una expiración insuficiente. El presupuesto por turno
se reinicia al comenzar otro turno; la ventana compartida solo se recupera al
expirar uso o liquidar solicitudes. El diagnóstico separa uso real/estimado,
reservas en vuelo, reservas de síntesis, disponibilidad y recuperación. Cuando
esta depende de llamadas en vuelo, el tiempo se registra como desconocido (`null`).
El ajuste de reserva a uso real ya evitaba el doble conteo en las respuestas
exitosas anteriores; los rechazos locales anteriores tampoco creaban reservas
nuevas. La fuga estaba en llamadas fallidas después de reservar, no en cada
`groq_budget`. Esta distinción evita borrar consumo real al limpiar un turno.

`tests/test_budget_regression.py` reproduce estos casos con reloj/usage simulados,
varios turnos, expiración exacta, concurrencia, cancelación y reintentos 429. Estos
tests no demuestran el comportamiento de la cuenta real ni cambian su cuota.

## Medición automatizada reproducible

Desde `apps/api`: `python -m pytest tests/test_efficiency.py -q`.
Los dos recorridos de comparación usan las mismas fuentes simuladas; el recorrido
granular reproduce la selección anterior, no ejecuta un binario histórico.
Su presupuesto se eleva **solo en esa prueba** para medir el recorrido completo.

| Escenario | Rondas LLM | Llamadas MCP | Entrada usage simulada | Salida usage simulada | Total simulado |
|---|---:|---:|---:|---:|---:|
| Comparación granular de tres películas | 8 | 7 | 14800 | 750 | 15550 |
| Comparación agrupada de tres películas | 2 | 1 | 4000 | 450 | 4450 |
| Recomendación de tres películas | 2 | 1 | 4000 | 450 | 4450 |
| Dos consultas independientes agrupadas | 2 | 2 | 4000 | 450 | 4450 |
| Búsqueda y detalles dependientes | 3 | 2 | 5800 | 500 | 6300 |

**Los contadores `usage` de esa tabla son entradas asignadas al mock** (1800/50 por
planificación, 2200/400 por síntesis). Validan contabilidad y presupuestos; no son
tokens tokenizados ni ahorro medido de producción. Las rondas y llamadas sí se
cuentan ejecutando el código real con Groq/HTTP simulados. No se estima latencia
de producción: la prueba de concurrencia usa demoras artificiales de 10 ms.

En el mismo replay, el tamaño total de solicitudes de comparación baja de 42424 a
7337 **caracteres**, y la heurística de entrada de 14364 a 2519 **tokens estimados**.
Son medidas separadas del `usage` simulado. Los datos del incidente aportados por
el usuario suman 9970 tokens de entrada y 195 de salida en cuatro respuestas
exitosas, antes de terminar; no son una medición después de esta corrección.

## Una prueba manual real pendiente

Esta corrección no realiza llamadas externas. Con las credenciales ya configuradas
localmente y `AGENT_PROVIDER=groq` en `apps/api/.env`, ejecutar desde la raíz:

```powershell
docker compose up --build -d
docker compose exec -T api python -c "from app.core.config import get_settings; print(get_settings().agent_provider)"
```

Esperar al menos 60 segundos desde la última respuesta Groq. En una conversación
nueva, enviar **una sola consulta**: «Recomiéndame tres películas de ciencia
ficción». Comprobar que después de MCP se entrega una respuesta final y las
tarjetas conservan sus datos. Revisar `docker compose logs --since 3m api`:
`groq_budget_admitted` muestra la salida reservada (hasta 1800), `groq_usage` el
consumo real y `groq_budget_released` debe dejar reserved_tokens en cero.
Si hay un bloqueo legítimo, `groq_budget_limited` muestra razón, disponibilidad y
recuperación. No imprimir configuración completa ni `.env`. Otras aplicaciones
de la organización todavía pueden consumir cuota; no asumir ausencia de 429.

La corrección del presupuesto no se ha probado con llamadas reales.
Las traducciones de títulos y resultados ambiguos pueden exigir otra búsqueda;
la coincidencia de título sigue sin verificar por sí sola una adaptación.
