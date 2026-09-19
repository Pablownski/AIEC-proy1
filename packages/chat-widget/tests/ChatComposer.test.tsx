import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ChatComposer } from "../src/components/ChatComposer";

describe("ChatComposer", () => {
  it("does not call onSend for empty or whitespace-only input", async () => {
    const onSend = vi.fn();
    const user = userEvent.setup();
    render(<ChatComposer onSend={onSend} />);

    await user.type(screen.getByLabelText("Escribe un mensaje"), "   ");
    await user.click(screen.getByRole("button", { name: "Enviar mensaje" }));

    expect(onSend).not.toHaveBeenCalled();
  });

  it("sends trimmed text and clears the input", async () => {
    const onSend = vi.fn();
    const user = userEvent.setup();
    render(<ChatComposer onSend={onSend} />);
    const textarea = screen.getByLabelText("Escribe un mensaje");

    await user.type(textarea, "  Hola  ");
    await user.click(screen.getByRole("button", { name: "Enviar mensaje" }));

    expect(onSend).toHaveBeenCalledWith("Hola");
    expect(textarea).toHaveValue("");
  });

  it("sends the message when Enter is pressed", async () => {
    const onSend = vi.fn();
    const user = userEvent.setup();
    render(<ChatComposer onSend={onSend} />);

    await user.type(screen.getByLabelText("Escribe un mensaje"), "Hola{Enter}");

    expect(onSend).toHaveBeenCalledWith("Hola");
  });

  it("inserts a newline instead of sending on Shift+Enter", async () => {
    const onSend = vi.fn();
    const user = userEvent.setup();
    render(<ChatComposer onSend={onSend} />);
    const textarea = screen.getByLabelText("Escribe un mensaje");

    await user.type(textarea, "linea1{Shift>}{Enter}{/Shift}linea2");

    expect(onSend).not.toHaveBeenCalled();
    expect(textarea).toHaveValue("linea1\nlinea2");
  });

  it("disables the input and send button while disabled=true", () => {
    render(<ChatComposer onSend={vi.fn()} disabled />);

    expect(screen.getByLabelText("Escribe un mensaje")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Enviar mensaje" })).toBeDisabled();
  });
});
