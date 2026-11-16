# Bloque 2 — Tarjetas y referencias de Damián

## Datos y compatibilidad

`ChatMessage` conserva texto, rol, ID y fecha y añade `metadata` opcional:
`movies`, `books`, `comparisons` y `actions`. HTTP y WebSocket comparten el mismo
esquema. Los transports validan formas, tamaños, referencias cruzadas y URLs.
Un servidor antiguo o MockAgent sigue funcionando sin metadatos.

El `Agent` original conserva `respond() -> str`. La capacidad opcional
`StructuredAgent.respond_with_metadata()` devuelve `AgentReply`; ChatService la
usa cuando existe. GroqAgent conserva también su método textual para consumidores
anteriores. Texto y metadatos se obtienen juntos dentro del lock de conversación,
sin una segunda llamada al modelo ni lecturas posteriores que puedan mezclar turnos.
Los reintentos de un turno ya completado conservan los IDs de acciones.

El modelo devuelve JSON de presentación con texto, IDs de obras y opinión. El
backend resuelve los IDs únicamente contra `ToolResult` reales de memoria/MCP.
No extrae títulos, pósteres ni URLs del Markdown. IDs desconocidos se descartan.
Si el modelo devuelve texto antiguo, se conserva y pueden mostrarse las obras
consultadas en ese turno, sin inventar una selección o relación bibliográfica.

Las comparaciones incluyen hechos de las fuentes, diferencias de fechas,
opinión del modelo etiquetada y limitaciones. Una relación solo se marca como
respaldada cuando coinciden el título normalizado y un autor de Books acreditado
por TMDB con el rol `Novel`. Las diferencias de escenas/fidelidad no se presentan
como verificadas. Traducciones, títulos distintos y créditos incompletos pueden
dejar adaptaciones reales como no confirmadas: es un criterio conservador, no una
base exhaustiva de relaciones. No se cambian MCP, cuotas ni límites del Bloque 1.

## Navegador

Solo al enviar una petición explícita de comparación/adaptación o apertura de
referencias se reservan hasta dos pestañas. Se reconocen acentos como «Compárala»
y «Ábreme IMDb»; solicitudes solo de IMDb o Books reservan un único destino.
Un saludo o recomendación corriente no reserva pestañas. La intención procede del
mensaje del usuario, nunca de descripciones de proveedores o texto del modelo.

La reserva utiliza ventanas nuevas sin nombre compartido y desconecta `opener`
inmediatamente, antes de navegar. Pasar `noopener` a `window.open` devolvería un
manejador nulo incluso si abrió la pestaña, impidiendo gestionar la reserva.
Los enlaces alternativos sí usan `target=_blank` y `rel=noopener noreferrer`.
No se reutilizan ventanas externas ni se usa `window.open` tras la espera asíncrona.

Solo se navega a URLs canónicas HTTPS de IMDb (`tt` + dígitos) y Google Books
(ID de volumen validado), construidas y validadas en backend y frontend. No se
aceptan subdominios parecidos, credenciales, query strings extra, fragmentos ni
esquemas arbitrarios. Cada acción se ejecuta como máximo una vez por widget.
Reservas sobrantes se cierran tras respuesta, fallo, desmontaje o 75 s de espera.
Una referencia bloqueada, cerrada o imposible de navegar ofrece un enlace visible.

Verificado en Chromium headless real: dos reservas y navegación a ambos destinos,
`opener=null`, ausencia de repetición, cierre de reservas sin acciones y enlaces
alternativos tras cerrar las reservas. También se retiró el argumento de Playwright
que deshabilita el bloqueo de popups: en este entorno abrió ambas referencias.
Los destinos y servicios fueron simulados localmente; no se llamó a APIs reales.
El bloqueo que devuelve `null` está cubierto en Vitest. Safari, Firefox, extensiones,
configuraciones de empresa y permisos particulares pueden bloquear una o ambas
pestañas: usar los enlaces alternativos o permitir popups para el sitio.

## Atribución

El pie de créditos muestra el aviso literal exigido por TMDB y su logo oficial,
menos prominente que Damián, sin modificar sus bytes, colores ni proporción. Se
empaqueta como data URI para evitar una dependencia de red al mostrar los créditos.
Fuente del SVG: https://files.readme.io/29c6fee-blue_short.svg, enlazado por la
documentación oficial. Reglas: https://developer.themoviedb.org/docs/faq.
Los pósteres y datos se atribuyen a TMDB; no se presentan como propiedad del proyecto.

## Verificación manual

1. Configurar Groq y catálogos como indica `docs/GROQ.md` y ejecutar
   `docker compose up --build -d`, con `AGENT_PROVIDER=groq` en `apps/api/.env`.
   Compose carga explícitamente ese archivo; no selecciona el proveedor desde el shell.
2. Pedir «Recomiéndame tres películas de fantasía»: revisar tarjetas, pósteres y
   calificaciones TMDB. Consultar también desde una pantalla pequeña.
3. Pedir «Compárala con su libro y dime si vale la pena verla»: revisar fuentes,
   autor, fechas, opinión y límites, así como IMDb/Books cuando existan referencias
   verificadas. Puede ser necesario concretar cuál de las tres películas.
4. Probar «Ábreme IMDb» para una película consultada con detalles. Sin IMDb ID no
   se inventa un enlace. Cerrar reservas o bloquear popups permite probar alternativas.
5. Con el override explícito `docker-compose.mock.yml` (ver `docs/GROQ.md`), comprobar
   el chat de texto y el cierre de reservas
   cuando la respuesta no incluye acciones.

Validaciones: pytest/Ruff/mypy desde `apps/api`; lint, typecheck, Vitest y build
desde la raíz. E2E: iniciar web y backend en modo mock y ejecutar `npm run e2e`.
`E2E_BASE_URL` permite otro puerto. `e2e/presentation.spec.ts` intercepta las APIs,
imágenes y referencias externas. Docker no estaba disponible en esta sesión; las
validaciones se hicieron localmente. Falta smoke test del JSON de presentación
generado por Groq real y validación manual en los navegadores de la presentación.
