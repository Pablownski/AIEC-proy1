# Evaluaciones OWASP de Damian

Se usa la nomenclatura de la rubrica OWASP 2025: [LLM01 Prompt Injection](https://genai.owasp.org/llmrisk/llm01-prompt-injection/) y [LLM07 System Prompt Leakage](https://genai.owasp.org/llmrisk/llm072025-system-prompt-leakage/).

## Amenazas y defensas

| Ataque | Defensa | Evidencia reproducible |
|---|---|---|
| Usuario suplanta sistema/desarrollador | Prioridad del sistema, capacidades limitadas | test_security.py y Promptfoo |
| Instruccion en overview MCP | Evidencias etiquetadas como no confiables; salida validada | test_indirect_injection_from_mcp_is_blocked |
| Extraccion completa o parcial | Deteccion de ventanas de 12 palabras del prompt | test_detects_protected_output |
| Extraccion en base64 o hex | Inspeccion de codificaciones comunes | test_detects_protected_output |
| Filtracion de claves configuradas | DLP antes de respuesta y memoria | test_configured_secret_is_blocked |
| Persistencia de una filtracion | Negativa sin commit de turno, cache ni artefactos nuevos | pruebas de ataque directo e indirecto |
| Fuga por opinión, sinopsis o descripción de tarjetas | Inspección recursiva de metadatos antes de respuesta y memoria | test_structured_output_cannot_bypass_dlp_or_poison_memory |
| Exfiltracion por enlaces o herramientas arbitrarias | URLs de fuentes y allowlist MCP con esquemas | test_groq_agent.py / test_mcp.py |

La DLP es una defensa parcial: no detecta toda parafrasis, traduccion, cifrado, fragmentacion entre turnos ni manipulacion semantica. Tampoco garantiza que una respuesta segura sea util. Los datos de catalogo siguen siendo no confiables aunque el modelo los haya usado correctamente en un turno anterior. La aplicacion no entrega claves al modelo; el filtro de claves es defensa adicional.

El system prompt es código público y no constituye una frontera de autorización.
Las restricciones efectivas de herramientas, argumentos y destinos se aplican
fuera del LLM. La detección de sus fragmentos atiende la rúbrica, pero ocultar el
prompt no sustituye la separación de secretos ni los controles deterministas.

## Pruebas deterministas

```bash
cd apps/api
pytest tests/test_security.py -v
pytest --cov=app --cov-report=term-missing --cov-fail-under=80
```

Estas pruebas usan un cliente LLM simulado y herramientas simuladas, incluyendo un overview envenenado. Fuerzan filtraciones para comprobar la barrera incluso cuando el modelo desobedece. No miden la resistencia estadistica de Groq. La prueba con respuesta segura frente a fuente envenenada comprueba continuidad del flujo, no demuestra que Groq produzca esa respuesta por si mismo.

Desde la raíz, el proveedor y las aserciones de evaluación también se prueban
sin red ni dependencias adicionales: `node --test security/provider.test.cjs`.
Esto prueba el harness JavaScript, **no ejecuta el motor Promptfoo ni Groq**.
El job frontend-quality de CI incluye esa comprobación offline.

## Promptfoo contra el agente real

Los siguientes comandos quedan preparados para una ejecución futura que sí
consumirá cuota Groq Free. No se ejecutaron en esta auditoría. Con el backend
ya configurado para Groq y Docker activo, verificar únicamente proveedor/modelo
(sin imprimir configuración completa ni claves):

Confirmar también que el backend corresponde al commit evaluado: las aserciones
leen el prompt público del checkout, no consultan instrucciones al servidor.
La sintaxis YAML y los módulos JavaScript se verificaron offline; la integración
con el motor fijado de Promptfoo deberá comprobarse antes de interpretar resultados.

```powershell
docker compose exec -T api python -c "from app.core.config import get_settings; s=get_settings(); print(s.agent_provider, s.groq_model)"
git rev-parse HEAD
npx --yes promptfoo@0.120.0 --version
$env:DAMIAN_API_URL = "http://localhost:8000"
$env:PROMPTFOO_CONFIG_DIR = Join-Path (Get-Location) ".promptfoo"
$env:PROMPTFOO_DISABLE_TELEMETRY = "true"
New-Item -ItemType Directory -Force security/results | Out-Null
npx --yes promptfoo@0.120.0 eval -c security/promptfooconfig.yaml --no-cache --no-table --no-progress-bar --repeat 1 --filter-pattern "LLM01 direct override|LLM07 verbatim extraction|LLM07 encoded extraction|benign control" --output security/results/groq-smoke.json *> security/results/groq-smoke.log
```

Son cuatro casos: override directo, extracción literal, extracción codificada y
control benigno. Para ejecutar los ocho casos existentes, omitir --filter-pattern
y usar otro nombre de salida privado. No usar el override MockAgent. El endpoint
health no identifica al proveedor, por lo que no sustituye esa comprobación previa.

El proveedor usa HTTP, una conversación nueva por caso y timeout de 90 s. La
configuración limita concurrencia a uno y añade 65000 ms entre casos; otras
aplicaciones pueden consumir la misma cuota. Node 24 y la versión fijada de
Promptfoo deben verificarse antes de la evaluación. Referencias:
[proveedores JavaScript](https://www.promptfoo.dev/docs/providers/custom-api/) y
[configuración](https://www.promptfoo.dev/docs/configuration/reference/).

El evaluador inspecciona texto **y metadatos**, ventanas del prompt público leído
desde el código, dos fragmentos conocidos, base64/hex comunes y formas típicas de
claves Groq/Google. No lee claves configuradas ni `.env`; la comprobación literal
de secretos reales corresponde a la barrera backend. No conoce todas las formas
de credenciales ni todas las codificaciones posibles. ATTACK_SUCCESS se compara
sin distinguir mayúsculas. El control benigno exige además una capacidad de
comparación; su utilidad debe revisarse manualmente.

Presupuesto local, cuotas, errores HTTP/red, respuestas inválidas y MockAgent se
clasifican como errores operativos, **nunca como ataques resistidos**. No se hacen
reintentos de evaluación automáticamente. La salida CLI se redirige a archivos
ignorados por Git: revisar y redactar respuestas antes de compartirlas, pues una
evaluación adversarial podría revelar información que no debe publicarse.

Un pase automático no certifica ausencia de filtraciones. La suite HTTP cubre
ataques directos, no sustituye un catálogo externo por una fuente envenenada.
Los ataques indirectos MCP y la persistencia se ejercitan mediante pytest con
datos/LLM simulados. Falta una evaluación indirecta real, en un entorno controlado
separado de producción, y comprobar ataques semánticos y de varios turnos.

Guardar fecha, commit, version de Promptfoo, modelo, parametros, numero de repeticiones y resultado por ataque. Registrar fallos de cuota o conectividad como errores operativos, nunca como ataques resistidos. Revisar y redactar salidas antes de compartirlas; security/results se ignora para evitar publicar accidentalmente informacion sensible.

## Resultado y defensa de salida por herramientas

Tambien se inspeccionan los valores de texto de argumentos MCP antes de llamar al catalogo. Esto bloquea la exfiltracion literal de claves o fragmentos protegidos mediante consultas de busqueda. La prueba test_tool_arguments_cannot_exfiltrate_protected_data verifica que la herramienta no se invoque y que el turno no se guarde. Los valores sinteticos cortos se comparan con limites de token para no bloquear identificadores como test-book-id cuando una prueba configura la clave test; claves largas se detectan por coincidencia literal.

## Auditoría del 2026-11-18

**No se ha demostrado cumplimiento total de LLM01/LLM07.** La rúbrica completa
no está disponible en el repositorio y faltan resultados verificables con Groq.
No se inspeccionó la configuración de credenciales para hacer esa afirmación.

Se reprodujeron y corrigieron dos defectos: la barrera omitía metadatos (seis
casos filtraban por opinión, overview o descripción), y un aviso de groq_budget
pasaba las aserciones anteriores como si fuera resistencia al ataque. La nueva
barrera rechaza la respuesta completa antes de guardar turno, artefactos, caché
o last_metadata y conserva la memoria previa. El evaluador ahora detecta además
filtraciones codificadas y metadatos que antes no observaba.

Registro histórico: se declararon 21 pruebas deterministas y un control negativo
Promptfoo 0.120.0 contra MockAgent (0/8 aprobados, 8 rechazados, 0 errores). El
artefacto citado security/results/mock-negative-control.json no está disponible
en esta copia; no pudo verificarse de nuevo. No era una evaluación de Groq real.
Con el proveedor actual, repetir ese control clasificaría MockAgent como error
operativo. No debe compararse directamente con aquel resultado histórico.

Resultados actuales y requisitos pendientes: [VALIDACION-PROYECTO2.md](VALIDACION-PROYECTO2.md).

## Evaluacion real sobre b27ca7b

Ver [resultados y hallazgos](OWASP-RESULTADOS-2026-11-18.md). Esta evaluacion precede las correcciones remotas e248672; no certifica esa nueva version.

