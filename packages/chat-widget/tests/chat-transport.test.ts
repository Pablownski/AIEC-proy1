import { describe, expect, it } from "vitest";
import { ChatTransportError } from "../src/transport/chat-transport";

describe("ChatTransportError", () => {
  it("carries a message and an optional cause", () => {
    const cause = new Error("network down");
    const error = new ChatTransportError("No pudimos enviar tu mensaje.", cause);

    expect(error).toBeInstanceOf(Error);
    expect(error.name).toBe("ChatTransportError");
    expect(error.message).toBe("No pudimos enviar tu mensaje.");
    expect(error.cause).toBe(cause);
  });

  it("works without a cause", () => {
    const error = new ChatTransportError("Falló");
    expect(error.cause).toBeUndefined();
  });
});
