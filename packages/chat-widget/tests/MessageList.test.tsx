import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MessageList } from "../src/components/MessageList";
import type { ChatMessage } from "../src/types/chat";

const userMsg: ChatMessage = {
  id: "1",
  role: "user",
  content: "Hola",
  createdAt: "2026-01-01T00:00:00.000Z",
};
const agentMsg: ChatMessage = {
  id: "2",
  role: "assistant",
  content: "**Hola** de vuelta",
  createdAt: "2026-01-01T00:00:01.000Z",
};

describe("MessageList", () => {
  it("renders user messages as plain text", () => {
    render(<MessageList messages={[userMsg]} agentName="Sofía" isAgentTyping={false} />);
    expect(screen.getByText("Hola")).toBeInTheDocument();
  });

  it("renders agent messages with markdown", () => {
    render(<MessageList messages={[agentMsg]} agentName="Sofía" isAgentTyping={false} />);
    expect(screen.getByText("Hola").tagName).toBe("STRONG");
  });

  it("keeps chronological order", () => {
    render(<MessageList messages={[userMsg, agentMsg]} agentName="Sofía" isAgentTyping={false} />);
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("Hola");
    expect(items[1]).toHaveTextContent("Hola de vuelta");
  });

  it("shows the typing indicator when isAgentTyping is true", () => {
    render(<MessageList messages={[]} agentName="Sofía" isAgentTyping />);
    expect(screen.getByText("Sofía está escribiendo...")).toBeInTheDocument();
  });

  it("hides the typing indicator when isAgentTyping is false", () => {
    render(<MessageList messages={[]} agentName="Sofía" isAgentTyping={false} />);
    expect(screen.queryByText("Sofía está escribiendo...")).not.toBeInTheDocument();
  });
});
