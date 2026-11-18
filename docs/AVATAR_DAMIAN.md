# Avatar animado de Damián

Los nueve PNG aprobados están en `packages/chat-widget/src/assets/damian/`.
Se extrajeron de `damian_avatar_8bits.zip` sin alterarlos; sus SHA-256 se
compararon con las entradas del ZIP. Todos conservan el lienzo original de
418 × 418 y su transparencia. El ZIP no forma parte del cambio versionado.

## Componentes y reutilización

- `DamianAvatar`: componente exportado del paquete, con estados `idle`,
  `thinking`, `talking`, `done`, `error`. Es controlado: el ciclo del chat decide
  cuándo termina cada estado. Puede usarse fuera del widget con `state` y `name`.
- `damian-sprites.ts`: importa directamente los nueve PNG. Adapta las URLs de
  Vite y los metadatos estáticos de Next.js, sin depender de `apps/web/public`,
  rutas absolutas del servidor ni servicios externos. La aplicación consumidora
  debe admitir imports PNG (integrados en Next.js/Vite). En Next.js, consumir
  desde un componente cliente y conservar `transpilePackages` para este paquete.
- `useChatPresentation`: conecta eventos del chat con estados y temporizadores.
- `RevealedMarkdown`: presentación progresiva sobre el resultado sanitizado.
- `useReducedMotion`: escucha la preferencia del sistema y sus cambios.

`ChatHeader` usa el avatar por defecto y mantiene el nombre/subtítulo configurados.
Un `avatarUrl` explícito conserva el comportamiento anterior para otras
integraciones. La caja mide entre 64 y 80 px según el viewport, con tamaño idéntico
en todos los estados, sin rotaciones, deformaciones, desplazamientos ni recortes.
La imagen usa `image-rendering: pixelated`. Los nueve recursos se precargan y
permanecen en la caché habitual del navegador; suman aproximadamente 1.1 MiB.

## Estados reales y tiempos

| Evento | Estado | Animación |
|---|---|---|
| Inicio o final del reposo | `idle` | `idle.png`, estático |
| Envío/reintento pendiente | `thinking` | `think_1` a `think_4`, cada **200 ms** |
| Respuesta recibida, texto revelándose | `talking` | `talk_1`/`talk_2`, cada **180 ms** |
| Final del revelado | `done` | `done.png`, **3000 ms**, luego idle |
| Rechazo del transporte | `error` | `error.png`, **3000 ms**, luego idle |

HTTP resuelve con el mensaje completo. WebSocket resuelve al recibir
`agent_message` seguido de `agent_end`; no transmite tokens. Ambos usan el mismo
flujo del widget. No se simula procesamiento ni se introduce streaming backend.

Cada envío incrementa un identificador local de operación. Los temporizadores y
callbacks antiguos no pueden modificar una operación más reciente. Un nuevo
envío interrumpe inmediatamente done, error o un revelado anterior; el mensaje
anterior conserva su contenido completo. Solo el último mensaje se anima, incluso
si un transporte reutiliza IDs de respuesta. Los intervalos y timeouts del avatar
se limpian al cambiar de estado o desmontarse el widget.

`useChat` ignora respuestas/rechazos tardíos de operaciones sustituidas y después
del desmontaje. Añade `cancel()` y `onCancel` opcional para cancelar la presentación
y descartar el resultado pendiente. Cambiar el transporte del widget cancela su
operación visual. Esta cancelación es local: no detiene el procesamiento backend
ni sustituye el contrato de cancelación propio de cada transporte. La UI sigue
impidiendo envíos concurrentes mientras espera una respuesta.

El avatar identifica como error un rechazo HTTP/red/WebSocket. Si el backend
devuelve un aviso de cuota dentro de una respuesta HTTP 200 normal, se presenta
como mensaje: no se intenta adivinar un estado de error analizando su texto.

## Revelado, accesibilidad y seguridad

El Markdown completo se procesa con el renderizador y la sanitización existentes,
y permanece oculto/inaccesible mientras se revela. De su árbol sanitizado se
extrae una copia de texto plano, presentada mediante texto React escapado: nunca
se interpreta Markdown parcial ni se usa `dangerouslySetInnerHTML`.

El avance ocurre cada **30 ms**, con lotes adaptados para terminar en un máximo
de **200 pasos (6000 ms)**. Se preservan caracteres Unicode completos. Al terminar
se muestra el Markdown íntegro con sus enlaces/listas/imágenes y las tarjetas y
comparaciones estructuradas originales. Un lector de pantalla recibe un estado
breve durante el revelado, en lugar de anunciar cada carácter; al terminar tiene
acceso al contenido completo.

Con `prefers-reduced-motion: reduce`, cada estado usa un solo sprite y el contenido
completo aparece inmediatamente. Se conserva la pausa estática de 3000 ms para
done/error. Cambiar esa preferencia durante el revelado también lo completa.
Los 3000 ms se programan con `setTimeout`; el navegador puede aplazar callbacks
en pestañas suspendidas o con el hilo principal bloqueado.

Las acciones verificadas de IMDb/Books siguen procesándose al recibir la respuesta,
sin esperar el revelado, para conservar reservas de pestañas y fallbacks existentes.
No se modifican contratos, backend, MCP, proveedores, secretos ni Docker.

## Comprobación

Desde la raíz:

```powershell
npm run typecheck
npm run lint
npm run test:coverage --workspace @agichat/chat-widget
npm run build
npm run start --workspace apps/web -- --port 3100
```

En otra terminal, con el servidor anterior activo:

```powershell
$env:E2E_BASE_URL = "http://localhost:3100"
npm run e2e -- e2e/avatar.spec.ts e2e/presentation.spec.ts
```

Esos E2E interceptan API, pósteres y referencias: no necesitan claves ni llaman
a Groq, TMDB o Books. Comprueban el navegador Chromium real, las nueve imágenes,
dimensiones estables en móvil, animación, error/reintento, movimiento reducido y
compatibilidad visual/acciones del Bloque 2. Los tests de unidad usan relojes
simulados para verificar los límites exactos, limpieza y respuestas tardías.

Para inspección manual, abrir la aplicación y enviar una consulta con el backend
ya disponible: observar baile, boca y celebración. Para provocar un error sin
depender de los proveedores, bloquear `/api/v1/chat` en las herramientas de red
del navegador; desbloquear y reintentar antes de 3 segundos. Emular movimiento
reducido en las herramientas de accesibilidad/renderizado y repetir. Una captura
móvil del recorrido automatizado se guarda en `test-results/` (no versionado).
