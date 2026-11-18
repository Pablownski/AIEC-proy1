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
| Exfiltracion por enlaces o herramientas arbitrarias | URLs de fuentes y allowlist MCP con esquemas | test_groq_agent.py / test_mcp.py |

La DLP es una defensa parcial: no detecta toda parafrasis, traduccion, cifrado, fragmentacion entre turnos ni manipulacion semantica. Tampoco garantiza que una respuesta segura sea util. Los datos de catalogo siguen siendo no confiables aunque el modelo los haya usado correctamente en un turno anterior. La aplicacion no entrega claves al modelo; el filtro de claves es defensa adicional.

## Pruebas deterministas

```bash
cd apps/api
pytest tests/test_security.py -v
pytest --cov=app --cov-report=term-missing --cov-fail-under=80
```

Estas pruebas usan un cliente LLM simulado y herramientas simuladas, incluyendo un overview envenenado. Fuerzan filtraciones para comprobar la barrera incluso cuando el modelo desobedece. No miden la resistencia estadistica de Groq. La prueba con respuesta segura frente a fuente envenenada comprueba continuidad del flujo, no demuestra que Groq produzca esa respuesta por si mismo.

## Promptfoo contra el agente real

Configurar apps/api/.env con AGENT_PROVIDER=groq y claves validas; iniciar Docker Compose. Confirmar el proveedor en el arranque antes de evaluar: el endpoint health no declara el proveedor. No usar el override mock para esta evaluacion.

```bash
npx promptfoo@0.120.0 eval -c security/promptfooconfig.yaml --no-cache --output security/results/live.json
```

El proveedor personalizado invoca el endpoint HTTP real con una conversacion nueva por caso, timeout de 90 segundos y concurrencia uno para respetar cuotas. DAMIAN_API_URL permite cambiar el backend. La version indicada fija el ejecutable de evaluacion; comprobar compatibilidad con el Node instalado. Referencias: [proveedores JavaScript](https://www.promptfoo.dev/docs/providers/custom-api/) y [configuracion](https://www.promptfoo.dev/docs/configuration/reference/).

Los casos incluyen override, suplantacion, abuso de herramientas y extraccion literal/parcial/codificada, ademas de un control benigno. Las aserciones detectan marcadores y fragmentos conocidos y rechazan varios errores operativos y respuestas mock; deben complementarse con revision humana de cada salida para evaluar parafrasis, utilidad y falsos positivos. Un pase automatico no certifica ausencia de filtraciones. Los ataques indirectos se reproducen actualmente en pytest; esta suite HTTP no reemplaza un catalogo externo por una fuente envenenada.

Guardar fecha, commit, version de Promptfoo, modelo, parametros, numero de repeticiones y resultado por ataque. Registrar fallos de cuota o conectividad como errores operativos, nunca como ataques resistidos. Revisar y redactar salidas antes de compartirlas; security/results se ignora para evitar publicar accidentalmente informacion sensible.

## Resultado y defensa de salida por herramientas

Tambien se inspeccionan los valores de texto de argumentos MCP antes de llamar al catalogo. Esto bloquea la exfiltracion literal de claves o fragmentos protegidos mediante consultas de busqueda. La prueba test_tool_arguments_cannot_exfiltrate_protected_data verifica que la herramienta no se invoque y que el turno no se guarde. Los valores sinteticos cortos se comparan con limites de token para no bloquear identificadores como test-book-id cuando una prueba configura la clave test; claves largas se detectan por coincidencia literal.

Resultado local: 21 pruebas de seguridad aprobadas. Promptfoo ejecuto los ocho casos contra MockAgent como control negativo: ocho rechazados, cero errores, resultado esperado por la asercion que excluye MockAgent. La resistencia de Groq real queda pendiente de credenciales y revision humana de sus respuestas. Consultar el registro completo y sus limitaciones en VALIDACION-PROYECTO2.md.
