# SKILLS (Claude CLI role prompts)

This folder contains role-specific “system prompt” style playbooks you can paste into Claude CLI to specialize the assistant.

## How to use
- Pick a role file in this folder.
- Paste its contents as your **system prompt** (or prepend it to your prompt).
- Then add your task and any repo-specific constraints.

## Suggested workflow
- **Single-role mode**: use one role file when you want a strong bias (e.g., networking deep-dive).
- **Hybrid mode**: start with `integration_expert.md` then add `llm_ai_engineer.md` or `orchestrator_state_engineer.md` depending on the task.

## Files
- `network_engineer.md`
- `systems_engineer_sre.md`
- `llm_ai_engineer.md`
- `orchestrator_state_engineer.md`
- `product_manager.md`
- `integration_expert.md`

## Notes
- These are intentionally opinionated toward this repo’s architecture: Docker Compose, gRPC services, tool-calling orchestrator, and UI.
- Each file ends with a short “Sources consulted” list (Perplexity MCP search results) so you can refresh/update as the project evolves.
