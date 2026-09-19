import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ChatWidget } from "../src/components/ChatWidget";
import { ChatTransportError } from "../src/transport/chat-transport";
import type { ChatMessage, ChatTransport } from "../src/index";

function makeTransport(impl: ChatTransport["sendMessage"]): ChatTransport {
  return { sendMessage: impl };
}

describe("ChatWidget", () => {
  it("renders the configured agent name, description and welcome message", () => {
    render(
      <ChatWidget
        agentName="Sofía"
        description="Tu asistente virtual"
        welcomeMessage="¡Hola! Soy tu asistente virtual Sofía."
        transport={makeTransport(vi.fn())}
      />,
    );

    expect(screen.getByRole("region", { name: "Chat con Sofía" })).toBeInTheDocument();
    expect(screen.getByText("Sofía")).toBeInTheDocument();
    expect(screen.getByText("Tu asistente virtual")).toBeInTheDocument();
    expect(screen.getByText("¡Hola! Soy tu asistente virtual Sofía.")).toBeInTheDocument();
  });

  it("renders an empty history when no welcome message is configured", () => {
    render(<ChatWidget agentName="Sofía" transport={makeTransport(vi.fn())} />);

    expect(screen.queryAllByRole("listitem")).toHaveLength(0);
  });

  it("uses the configured placeholder on the composer", () => {
    render(
      <ChatWidget
        agentName="Sofía"
        placeholder="Escribe una pregunta..."
        transport={makeTransport(vi.fn())}
      />,
    );

    expect(screen.getByPlaceholderText("Escribe una pregunta...")).toBeInTheDocument();
  });

  it("sends a message through the injected transport and renders the reply", async () => {
    const reply: ChatMessage = {
      id: "2",
      role: "assistant",
      content: "Hola de vuelta",
      createdAt: "2026-01-01T00:00:01.000Z",
    };
    const sendMessage = vi.fn().mockResolvedValue(reply);
    const user = userEvent.setup();
    render(<ChatWidget agentName="Sofía" transport={makeTransport(sendMessage)} />);

    await user.type(screen.getByLabelText("Escribe un mensaje"), "Hola{Enter}");

    expect(sendMessage).toHaveBeenCalledTimes(1);
    expect(await screen.findByText("Hola de vuelta")).toBeInTheDocument();
  });

  it("shows a retry button and safe error message when the transport fails", async () => {
    const sendMessage = vi.fn().mockRejectedValue(new ChatTransportError("Backend no disponible"));
    const user = userEvent.setup();
    render(<ChatWidget agentName="Sofía" transport={makeTransport(sendMessage)} />);

    await user.type(screen.getByLabelText("Escribe un mensaje"), "Hola{Enter}");

    expect(await screen.findByRole("alert")).toHaveTextContent("Backend no disponible");
    expect(screen.getByRole("button", { name: "Reintentar" })).toBeInTheDocument();
  });
});
