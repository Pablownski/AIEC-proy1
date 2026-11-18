import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

const api = process.env.E2E_API_URL ?? "http://localhost:8000";

test("HTTP and WebSocket preserve the chat contract against real services", async ({ request, page }) => {
  test.setTimeout(120000);
  const conversationId = randomUUID();
  const response = await request.post(`${api}/api/v1/chat`, {
    data: { conversation_id: conversationId, message: { role: "user", content: "Hola" } },
  });
  expect(response.ok()).toBeTruthy();
  const body = await response.json();
  expect(body.conversation_id).toBe(conversationId);
  expect(body.message.role).toBe("assistant");
  expect(body.message.content.length).toBeGreaterThan(0);
  await page.goto("/");
  const events = await page.evaluate(async ({ api, conversationId }) => {
    return await new Promise<Array<{ type: string; message?: { role: string; content: string }; conversation_id?: string }>>((resolve, reject) => {
      const socket = new WebSocket(`${api.replace(/^http/, "ws")}/ws/chat`);
      const received: Array<{ type: string; message?: { role: string; content: string }; conversation_id?: string }> = [];
      const timer = setTimeout(() => { socket.close(); reject(new Error("WebSocket timeout")); }, 90000);
      socket.onopen = () => socket.send(JSON.stringify({ conversation_id: conversationId, content: "Hola" }));
      socket.onerror = () => { clearTimeout(timer); reject(new Error("WebSocket connection failed")); };
      socket.onmessage = (event) => {
        const message = JSON.parse(event.data);
        received.push(message);
        if (message.type === "agent_end" || message.type === "error") {
          clearTimeout(timer);
          socket.close();
          resolve(received);
        }
      };
    });
  }, { api, conversationId });
  expect(events.map((event) => event.type)).toEqual(["agent_start", "agent_message", "agent_end"]);
  expect(events[1].conversation_id).toBe(conversationId);
  expect(events[1].message?.role).toBe("assistant");
  expect(events[1].message?.content).toBe(body.message.content);
});
