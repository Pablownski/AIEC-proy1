import { HttpChatTransport, type ChatTransport, type ChatWidgetConfig } from "@agichat/chat-widget";

export const chatWidgetConfig: ChatWidgetConfig = {
  agentName: "Damián",
  description: "Asistente de IA para cine y libros",
  placeholder: "Escribe una pregunta...",
  welcomeMessage: "¡Hola! Soy Damián, tu asistente de inteligencia artificial. Puedo recomendar películas y comparar adaptaciones con sus libros usando fuentes verificables. ¿Qué te gustaría descubrir?",
};

export function createChatTransport(): ChatTransport {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  return new HttpChatTransport({ baseUrl });
}
