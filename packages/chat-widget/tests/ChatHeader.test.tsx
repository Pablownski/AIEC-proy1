import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ChatHeader } from "../src/components/ChatHeader";

describe("ChatHeader", () => {
  it("renders the agent name", () => {
    render(<ChatHeader agentName="Sofía" />);
    expect(screen.getByText("Sofía")).toBeInTheDocument();
  });

  it("renders the description when provided", () => {
    render(<ChatHeader agentName="Sofía" description="Tu asistente virtual" />);
    expect(screen.getByText("Tu asistente virtual")).toBeInTheDocument();
  });

  it("omits the description paragraph when not provided", () => {
    const { container } = render(<ChatHeader agentName="Sofía" />);
    expect(container.querySelector(".agichat-header__description")).not.toBeInTheDocument();
  });

  it("uses the configured avatar URL", () => {
    const { container } = render(
      <ChatHeader agentName="Sofía" avatarUrl="https://example.com/avatar.png" />,
    );
    expect(container.querySelector("img")).toHaveAttribute(
      "src",
      "https://example.com/avatar.png",
    );
  });
});
