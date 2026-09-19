export type MessageRole = "user" | "assistant" | "system";

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  createdAt: string;
}

export type ChatStatus = "idle" | "sending" | "receiving" | "error";

export interface ChatWidgetConfig {
  agentName: string;
  description?: string;
  avatarUrl?: string;
  placeholder?: string;
  welcomeMessage?: string;
}
