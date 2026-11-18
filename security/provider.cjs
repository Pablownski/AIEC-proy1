const { randomUUID } = require("node:crypto");

module.exports = class DamianProvider {
  id() { return "damian-http-live"; }
  async callApi(prompt) {
    const base = process.env.DAMIAN_API_URL || "http://localhost:8000";
    const health = await fetch(`${base}/api/v1/health`, { signal: AbortSignal.timeout(10000) });
    if (!health.ok) throw new Error(`Health HTTP ${health.status}`);
    const response = await fetch(`${base}/api/v1/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ conversation_id: `security-${randomUUID()}`, message: { role: "user", content: prompt } }),
      signal: AbortSignal.timeout(90000),
    });
    if (!response.ok) throw new Error(`Chat HTTP ${response.status}`);
    const data = await response.json();
    return { output: data.message.content };
  }
};
