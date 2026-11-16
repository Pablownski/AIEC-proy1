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
sobrecarga por mensaje, y se reservan 1800 tokens de salida (incluido razonamiento).
**Es una heurística prudente, no el tokenizer GPT-OSS ni una cota garantizada.**
Cuando existe `usage`, sus contadores reales sustituyen la reserva. Sin `usage`
se conserva la reserva completa. No se confunden caracteres y tokens.

El cliente compartido mantiene uso y reservas en vuelo de los últimos 60 segundos,
incluidas otras conversaciones del mismo proceso. Espera a liberar la ventana solo
si cabe la espera más el timeout HTTP; vuelve a comprobar el presupuesto. No hay
esperas indefinidas. Si otra ronda de investigación no cabe y hay artefactos, se
intenta una síntesis más barata sin esquemas; si tampoco cabe, devuelve el mensaje
seguro de límite y no guarda el turno. Una síntesis limitada explicita lo pendiente.

Se conserva **un único reintento por turno** exclusivamente para TPM/RPM explícitos,
respetando `retry-after` y la duración restante. Nunca se reintentan automáticamente
límites diarios/desconocidos. El SDK no añade reintentos propios. Un error de cuota
de Books sigue abortando sin guardar turnos, cachés ni metadatos incompletos.

`groq_usage`, `groq_budget_wait`, `groq_budget_limited` y los eventos del agente
permiten correlacionar rondas, uso real, estimación y decisión mediante `run_id`.
Solo registran contadores/códigos: sin conversaciones, argumentos, URLs con claves,
credenciales ni system prompt. Las cuotas son de organización y pueden consumirse
desde otros procesos: este contador local no garantiza evitar todos los 429.
[Referencia de Groq](https://console.groq.com/docs/rate-limits).

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

En una conversación nueva, enviar **una sola consulta**:
«Compara la película TMDB 671 con su libro original y dime si vale la pena verla;
abre sus referencias». Comprobar póster, relación sustentada o limitación explícita,
referencias IMDb/Books y alternativa del navegador si bloquea pestañas. Revisar
`docker compose logs --since 3m api`: herramienta `compare_movies`, rondas,
`groq_usage` y eventuales límites, sin imprimir configuración completa ni `.env`.
Esperar la recuperación de cuota antes de esta única prueba; registrar el `usage`
real y no asumir que serán exactamente dos rondas ni que nunca aparecerá un 429.

No se ha probado aún la selección de la nueva herramienta con el modelo real.
Las traducciones de títulos y resultados ambiguos pueden exigir otra búsqueda;
la coincidencia de título sigue sin verificar por sí sola una adaptación.
