"""A deterministic mock agent used until a real agent lands in Proyecto 2."""

from __future__ import annotations

import asyncio

_GREETINGS = ("hola", "buenas", "hey", "hi", "hello")

_FEATURES_REPLY = """\
Claro. Aquí tienes un ejemplo:

## AGIChat

Puedes instalar el widget utilizando:

`npm install @agichat/chat-widget`

### Características

- Integración sencilla
- Markdown
- Comunicación HTTP/WebSocket
"""


class MockAgent:
    """Simulates an agent's response, including a realistic processing delay."""

    def __init__(self, delay_seconds: float = 0.4) -> None:
        self._delay_seconds = delay_seconds

    async def respond(self, message: str, conversation_id: str) -> str:
        cleaned = message.strip()
        if not cleaned:
            raise ValueError("message must not be empty")

        if self._delay_seconds:
            await asyncio.sleep(self._delay_seconds)

        lowered = cleaned.lower()
        if any(lowered.startswith(g) for g in _GREETINGS):
            return "¡Hola! Soy tu asistente virtual. ¿En qué puedo ayudarte hoy?"

        if "agichat" in lowered or "caracterí" in lowered or "feature" in lowered:
            return _FEATURES_REPLY

        return (
            f"Recibí tu mensaje:\n\n{cleaned}\n\n"
            "Todavía soy un agente simulado (`MockAgent`), pero pronto seré reemplazado "
            "por un agente real sin cambios en el widget."
        )
