export { ChatWidget } from "./components/ChatWidget";
export type { ChatWidgetProps } from "./components/ChatWidget";
export { ChatHeader } from "./components/ChatHeader";
export { MessageList } from "./components/MessageList";
export { UserMessage } from "./components/UserMessage";
export { AgentMessage } from "./components/AgentMessage";
export { ChatComposer } from "./components/ChatComposer";
export { TypingIndicator } from "./components/TypingIndicator";

export { useChat } from "./hooks/useChat";
export type { UseChatOptions, UseChatResult } from "./hooks/useChat";

export type { ChatTransport } from "./transport/chat-transport";
export { ChatTransportError } from "./transport/chat-transport";
export { HttpChatTransport } from "./transport/http-transport";
export type { HttpChatTransportOptions } from "./transport/http-transport";

export type { ChatMessage, ChatStatus, ChatWidgetConfig, MessageRole } from "./types/chat";
