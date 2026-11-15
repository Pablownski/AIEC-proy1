# Cliente Groq — Fase 1

`apps/api/app/clients/groq_client.py` encapsula `AsyncGroq` del SDK oficial.
No está conectado a las rutas: el chatbot sigue utilizando `MockAgent`.

Configurar únicamente `apps/api/.env` con las variables indicadas en
`.env.example`: `GROQ_API_KEY` y `GROQ_MODEL` (predeterminado:
`openai/gpt-oss-120b`). La clave es opcional al arrancar la aplicación;
solo se exige al construir `GroqClient`. `Settings` la protege con `SecretStr`.
No imprimir la clave ni activar logs detallados del SDK en entornos con secretos.

El cliente recibe `Settings` y ofrece `complete(messages)`, con los tipos de
mensajes del SDK. Devuelve un `ChatCompletion` completo, conservando contenido,
uso y posibles `tool_calls`. Todavía no envía definiciones de herramientas ni
ejecuta funciones. Un agente posterior podrá consumir esta interfaz sin cambiar
los contratos actuales de chat.

Reutilizar una instancia dentro de `async with GroqClient(settings)` o cerrarla
con `await client.close()` al finalizar su ciclo de vida. El timeout de E/S
predeterminado es 10 segundos, configurable mediante `timeout_seconds` positivo
y finito. Se deshabilitan los reintentos automáticos para evitar multiplicar
solicitudes y latencia. Esto no constituye un límite total de duración del turno.

`GroqClientError.code` distingue `configuration`, `timeout`, `connection`,
`authentication`, `rate_limit`, `provider` y `response`. Los mensajes son fijos;
no incluyen cuerpos, cabeceras ni detalles de excepciones del proveedor.
Una respuesta sin opciones o sin contenido ni herramientas produce `response`.

Las pruebas usan un SDK simulado, deshabilitan la lectura de `.env` antes de
importar la aplicación y bloquean el transporte HTTP externo de httpx.
Ejecutar desde `apps/api`: `pytest --cov=app --cov-fail-under=80`.
No se ha verificado disponibilidad del modelo, cuotas ni credenciales mediante
llamadas reales. Esta fase no requiere activar facturación.

Referencia: [SDK oficial de Groq](https://github.com/groq/groq-python).
