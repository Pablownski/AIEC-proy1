const { randomUUID } = require("node:crypto");
const { operationalKind } = require("./assertions.cjs");

module.exports = class DamianProvider {
  id() { return "damian-http-live"; }
  async callApi(prompt) {
    await new Promise((resolve) => setTimeout(resolve, Number(process.env.DAMIAN_EVAL_DELAY_MS ?? 20000)));
    const base = process.env.DAMIAN_API_URL || "http://localhost:8000";
    const health = await fetch(`${base}/api/v1/health`, { signal: AbortSignal.timeout(10000) })
      .catch(() => { throw new Error("operational: health network or timeout"); });
    if (!health.ok) throw new Error(`operational: Health HTTP ${health.status}`);
    const response = await fetch(`${base}/api/v1/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ conversation_id: `security-${randomUUID()}`, message: { role: "user", content: prompt } }),
      signal: AbortSignal.timeout(90000),
    }).catch(() => { throw new Error("operational: chat network or timeout"); });
    if (!response.ok) throw new Error(`operational: Chat HTTP ${response.status}`);
    const data = await response.json().catch(() => { throw new Error("operational: invalid JSON"); });
    if (!data?.message || typeof data.message.content !== "string") throw new Error("operational: invalid message");
    const kind = operationalKind(data.message.content);
    if (kind) throw new Error(`operational: ${kind}`);
    // Grade all browser-visible fields, not just the main text.
    return { output: JSON.stringify({ content: data.message.content, metadata: data.message.metadata ?? null }) };
  }
};
