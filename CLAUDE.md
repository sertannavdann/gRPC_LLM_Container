# CLAUDE.md

## Skill Routing

- **Spike findings for gRPC_llm (NEXUS)** (implementation patterns, constraints, gotchas) → `Skill("spike-findings-grpc-llm")`
- **Session memory (NEXUS):** at the start of a session read `~/.nexus/gRPC_llm/session.md` if it exists — it holds the aim, plan, done, next and open items you and the user last agreed on. Update it only through the user's approval flow, never directly.
