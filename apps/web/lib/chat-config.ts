import { HttpChatTransport, type ChatTransport, type ChatWidgetConfig } from "@agichat/chat-widget";

export const chatWidgetConfig: ChatWidgetConfig = {
  agentName: "Damián",
  description: "Tu asistente virtual",
  placeholder: "Escribe una pregunta...",
  welcomeMessage: "¡Hola! Soy tu asistente virtual Damián. ¿En qué puedo ayudarte hoy?",
};

export function createChatTransport(): ChatTransport {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  return new HttpChatTransport({ baseUrl });
}
