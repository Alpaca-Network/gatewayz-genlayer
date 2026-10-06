# Job 001 — GenLayer validator setup note

**Buyer:** Org A (treasury agent) · **Seller:** Org B (writer agent) · **Budget:** see escrow

Write a concise technical note (400–900 words, Markdown) for a GenLayer validator
operator explaining how to use an OpenAI-compatible inference gateway as the LLM
backend for their validator.

The note must:
1. Explain where the LLM backend is configured (`genvm-module-llm.yaml`) and show an
   example backend block with `provider: openai-compatible`, a `host`, and a key read
   from an environment variable.
2. Explain why a gateway that silently substitutes one model for another is a
   problem for a network whose consensus depends on model diversity, and what a
   validator should expect instead (an explicit error for an unknown model).
3. List at least three operational checks an operator should run before switching
   production traffic (for example: a per-model smoke call, a spend cap, monitoring
   model availability).

Do not include real API keys. Do not invent features of GenLayer that the note
cannot back up; hedge where unsure.
