# gRPC_llm — pruned to what one user on one Mac runs

Audit: `../nexus-voice/docs/VALUE_AUDIT.md`. Full history: tag `v2.15-full`, branch `attic/2026-11`.

What is left (about 2 k lines):

```
tools/builtin/web_search.py, web_loader.py    actions a spoken turn can ask for (Serper search, page fetch)
sandbox_service/policy.py, runner.py          run untrusted Python with import and network policy
shared/modules/static_analysis.py, security_policy.py, credentials.py   sandbox support; Fernet credential store
shared/clients/llm_client.py                  client for the llm-tiers runtime (../llm-tiers, gRPC on localhost)
tests/                                        web tools + sandbox tests
```

Removed from main (still in the attic): Docker Compose and 13 services, the LangGraph orchestrator and
self-consistency, module lifecycle and admin API, auth, billing, audit, observability, eight cloud providers
and the router, RL, the Next.js UI, dashboard, MCP bridge, Chroma, the GSD planning tree, strategy docs.
Each comes back only when a specific spoken turn, written as a test in nexus-voice, cannot pass without it.

```
make test
make llm-status      # tiers run from ../llm-tiers
```
