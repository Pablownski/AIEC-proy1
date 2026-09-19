import { describe, expect, it } from "vitest";
import { PACKAGE_NAME } from "../src/index";

describe("bootstrap", () => {
  it("exposes the package entrypoint", () => {
    expect(PACKAGE_NAME).toBe("@agichat/chat-widget");
  });
});
