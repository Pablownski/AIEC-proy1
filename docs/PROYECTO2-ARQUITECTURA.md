# Arquitectura de Damian: Proyecto 2

## HLD: sistema desplegado

```mermaid
flowchart LR
  U[Usuario] --> W[Next.js / SDK React]
  W --> T[ChatTransport HTTP o WebSocket]
  T --> A[FastAPI: REST /api/v1 y /ws/chat]
  A --> S[ChatService / Agent Protocol]
  S --> G[GroqAgent]
  G --> L[Groq API]
  G --> M[Memoria local TTL / LRU]
  G --> C[Cliente MCP]
  C --> P[Subproceso MCP por turno: STDIO]
  P --> TM[TMDB API]
  P --> B[Google Books API]
  G --> D[Barrera de salida / seleccion / URLs verificadas]
  D --> A
```

Docker Compose ejecuta web y api; MCP se ejecuta como subproceso de api, no como un tercer servicio. Solo api recibe el archivo de credenciales. El navegador consume contratos de chat y metadatos; nunca ejecuta logica del agente. La demo usa HTTP; el SDK tambien ofrece WebSocket. WebSocket emite eventos de inicio, mensaje completo y fin: no es streaming de tokens.

## LLD: componentes y ejecucion

```mermaid
sequenceDiagram
  participant UI as ChatWidget / useChat
  participant T as ChatTransport
  participant API as FastAPI / ChatService
  participant G as GroqAgent
  participant M as ConversationMemory
  participant L as GroqClient / RequestBudget
  participant MCP as MCPTools / catalogo
  UI->>T: enviar mensaje
  T->>API: HTTP o WS
  API->>G: respond_with_metadata
  G->>M: turn(id), lock y limite de solicitudes
  G->>MCP: descubrir herramientas permitidas
  loop hasta limite de rondas / tiempo / llamadas
    G->>L: sistema + dialogo + evidencias no confiables
    L-->>G: respuesta o tool_calls
    opt llamadas a herramientas
      G->>MCP: nombre permitido + argumentos validados
      MCP-->>G: ToolResult tipado / fuentes verificadas
    end
  end
  G->>G: parse_selection + DLP + filtro de URLs
  alt salida protegida
    G-->>API: negativa fija sin guardar turno
  else turno completo y sin fallos
    G->>M: commit de dialogo, artefactos, cache y metadatos
    G-->>API: AgentReply
  end
  API-->>T: contrato de respuesta / eventos
  T-->>UI: Markdown sanitizado, tarjetas y avatar
```

`context.py` proyecta evidencias acotadas y reutiliza consultas mediante claves normalizadas. `memory.py` conserva hasta seis turnos, 12 artefactos y 12 entradas de cache; capacidad predeterminada de 128 conversaciones y TTL de 900 segundos. Serializa turnos por conversacion. `GroqAgent` limita ocho turnos activos y ocho llamadas MCP, con concurrencia de herramientas de dos y consultas Books serializadas. `GroqClient` controla presupuestos y diagnosticos; los errores privados no llegan al widget.

Las seis herramientas permitidas son search_movies, discover_movies, movie_details, search_books, book_details y compare_movies. MCP valida nombre, esquema JSON y modelos Pydantic; no admite comandos o URLs arbitrarias. `presentation.py` deriva tarjetas de artefactos consultados; la interfaz no debe interpretar texto del modelo como acciones privilegiadas.

## Decisiones y escalabilidad

La interfaz Agent permite reemplazar proveedores sin alterar rutas. ChatTransport permite cambiar la comunicacion sin modificar componentes visuales. Los catalogos aportan fuentes verificables y los presupuestos acotan latencia, costo y carga.

El estado actual es de una instancia: memoria, locks, cache y limites son locales al proceso. Agregar replicas sin cambiar esto perderia continuidad y permitiria superar limites. Para escalar: introducir un almacenamiento compartido con TTL (por ejemplo Redis), locks distribuidos y limites globales por proveedor; separar cache de catalogo de memoria conversacional. Un balanceador debe soportar Upgrade de WebSocket y cierre ordenado de conexiones. Afinidad de sesion puede ser una transicion, pero no resuelve reinicios ni cuotas compartidas.

Separar MCP en un servicio persistente exige sustituir STDIO por un transporte autenticado y limitar su red a los catalogos. Mantener cuotas y backpressure antes de aumentar replicas; medir p95, errores 429, uso de tokens y saturacion. Redis, balanceador y MCP remoto son propuestas, no infraestructura implementada.

Los identificadores de conversacion no constituyen autenticacion. Un despliegue multiusuario requiere identidad autenticada y autorizacion del propietario antes de acceder a memoria. No almacenar secretos en prompts; la confidencialidad no puede depender de instrucciones al modelo.

Antes de ejecutar MCP, el agente inspecciona los argumentos de texto con la misma barrera de datos protegidos utilizada para la salida. Una coincidencia evita la llamada externa y marca el turno como fallido, sin persistirlo.
