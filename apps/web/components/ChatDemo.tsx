"use client";

import { ChatWidget } from "@agichat/chat-widget";
import { useMemo } from "react";
import { chatWidgetConfig, createChatTransport } from "../lib/chat-config";

export function ChatDemo() {
  const transport = useMemo(() => createChatTransport(), []);

  return <ChatWidget {...chatWidgetConfig} transport={transport} />;
}
