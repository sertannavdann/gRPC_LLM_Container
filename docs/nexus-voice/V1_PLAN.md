# NEXUS Voice — v1 implementation plan

Companion to `RESEARCH.md` (facts) and its §11 (decisions). v1 success criterion, unchanged:

> "Hey Siri, open NEXUS" → the app connects over WireGuard → you say *"what's the state of gRPC_llm"*
> → the Mac answers in 2–3 spoken sentences from local models, **zero cloud tokens**, after an Arm
> step that locked the scope, engine and power for the session.

Anything not on the path to that sentence is not in v1.

## Principles

1. **Arm before Run.** No model reads anything until the manifest is approved on the phone.
2. **Rulesets first, inference second.** Repo, power, path access and loop control are deterministic
   and set in the HMI. Models propose intent (Listener), prose (Reporter) and document deltas (Keeper).
3. **Local models never write to a repo.** They write only the session document, and only after the
   user approves the delta in the app.
4. **Text crosses the wire.** STT/TTS on the phone (iOS 26 SpeechAnalyzer, AVSpeechSynthesizer).
5. **Testable without the phone.** Every nexusd capability is reachable from a CLI client first.

## Repository: `nexus-voice` (new)

```
nexus-voice/
  README.md
  docs/                 RESEARCH.md, V1_PLAN.md, MANIFEST.md (schema), THREAT_MODEL.md (1 page)
  llm/                  lifted from gRPC_llm, unchanged behaviour:
    engines/ llm.proto llm_service.py config.py model_registry.py
    supervisor.sh  config/tiers/{standard-mlx,standard,heavy}.env
    llm_bench.py llm_stability.py  tests/
  nexusd/               Python 3.12, uv-managed, one process
    __main__.py         `python -m nexusd` → gateway on the WireGuard address only
    gateway.py          HTTP + SSE (stdlib http.server or a 1-dep ASGI; decide at M1)
    inventory.py        system overview: CPU/GPU/ANE W (if helper), GPU %, thermal state, mem, disk, tiers, Docker
    scope.py            allowlist (realpath + prefix), sandbox-exec profile generator
    manifest.py         compose / canonicalise / sha256 / verify; arm/disarm state machine
    facts.py            collectors (code only): git, claude sessions-index + jsonl tail, test logs, tiers
    listener.py         keyword grammar → else 3B intent proposal (ChatML, fences stripped)
    reporter.py         3B spoken text, strict length, "you" not "the team"
    keeper.py           3B structured delta → pending approval → apply to session.md
    executor.py         (v1.1) claude -p wrapper, Max plan, --restricted, --max-turns, JSON result
    session/            store (~/.nexus/<repo>/session.md + manifest.json + ledger.jsonl), redaction
    tiers.py            gRPC client to llm tiers; on-demand start, idle-stop timer
    telemetry.py        client for the root helper's socket; joules accumulator; history ring
    cli.py              `nexus arm|turn|status|keeper-approve` for development and user tests
  helper/               tiny root LaunchDaemon: powermetrics -f plist → unix socket (Python, no deps)
  ios/NEXUS/            Xcode project, iOS 26, Swift
    App/                AppIntent "Open NEXUS", scenes
    Arm/                Inventory, Scope tree, Engine, Power, Limits, Loop, Lockstep views
    Talk/               TurnLoop (DictationTranscriber → /turn → SSE → AVSpeechSynthesizer)
    Net/                WireGuardKit tunnel manager, SSEClient (raw-bytes parser, heartbeat, backoff)
    Session/            read-only session.md view, Keeper approval sheet, ledger
  deploy/
    wireguard/          keygen.sh, server.conf template, phone.conf → QR
    launchd/            com.nexus.helper.plist, com.nexus.nexusd.plist (ProcessType Interactive)
    install.sh          brew wireguard-tools, venvs, plists
```

## Protocol (phone ↔ nexusd, inside the tunnel)

| Method | Path | Purpose |
|---|---|---|
| GET | `/inventory` | Arm screen data (no model, no repo read) |
| GET | `/scope/tree?root=` | directory listing of allowed roots only |
| POST | `/manifest/compose` | body: scope/engine/power/limits/loop → returns manifest + hash |
| POST | `/manifest/arm` | body: hash → arms; starts allowed tiers that are marked warm |
| POST | `/manifest/disarm` | stops tiers, clears state |
| POST | `/turn` | body: `{text, hash, power}` → SSE: `intent`, `facts`, `say` (token chunks), `keeper_pending`, `done`, `error` |
| POST | `/keeper/approve` | body: `{delta_id, accept|edit}` → applies to session.md |
| GET | `/session` | current session.md + ledger |
| GET | `/telemetry` | SSE: 1 Hz samples (W by rail, GPU %, thermal, joules, tiers) |

Heartbeat comment every 15 s on every SSE stream (iOS idle timeout is 60 s).

## Turn pipeline (power 1)

```
text ─► rules: end word? power change? repo named & allowed? ─► Listener (3B) intent proposal
     ─► facts.collect(manifest.scope, repo)              (code, ~50 ms: git, sessions-index, tiers, tests)
     ─► Reporter (3B) streams `say` chunks               (~0.6 s)       ← the phone speaks these
     ─► Keeper (3B) proposes delta                       (~0.6 s, after say) → `keeper_pending`
     ─► app shows delta; approve → session.md updated; ledger line written
```

Budget for "stop talking → first spoken word": ≤ 1.5 s warm, ≤ 5 s when the MLX tier has to load.

## Milestones

**M0 — Skeleton + lift (½ day).** New repo; move `llm/` from gRPC_llm with its tests; `make llm-up/-stability` green in the new home. gRPC_llm keeps its copy until v1 ships, then points at nexus-voice.

**M1 — nexusd core, CLI-driven (2–3 days).** inventory (without watts), scope, manifest, facts,
listener, reporter, keeper-delta, session store, tiers on-demand/idle-stop, gateway bound to a loopback
address for now. Done when `nexus arm --repo gRPC_llm --power 1 && nexus turn "what's the state of
gRPC_llm"` prints the spoken text and a pending delta, with the manifest hash enforced.
Tests: unit for scope/manifest/facts/rules with fakes; a stability-style soak for 50 turns.

**M2 — Telemetry (1 day).** Root helper LaunchDaemon streaming `powermetrics -f plist` at 1 Hz;
nexusd adds ioreg GPU % and `thermalState`; `/telemetry` SSE; joule accumulator; pause rule on
thermal ≥ serious. Done when `nexus status` shows W by rail and GPU % while a turn runs.

**M3 — Transport (1 day).** `wireguard-tools` on the Mac, server config, UDP port-forward on the
router, dynamic DNS; nexusd binds to the wg address; phone config as QR. Done when a laptop on
cellular tethering reaches `/inventory` through the tunnel and nothing answers on the LAN address.

**M4 — iOS app (4–6 days).** Tunnel (WireGuardKit), Arm screens, Talk loop (DictationTranscriber
with `AnalysisContext` vocabulary → `/turn` → SSE → AVSpeechSynthesizer), Keeper approval sheet,
session view, "Open NEXUS" App Shortcut. Done when the v1 sentence works end-to-end on the phone.

**M5 — User tests (ongoing).** Turkish on-device locale, vocabulary accuracy for repo/tool names,
loop ergonomics (silence timeout, end word), Keeper approval friction, power/thermal readings vs
expectation. Findings go to `docs/USER_TESTS.md` and drive v1.1.

**v1.1 (after the sentence works).** `executor.py`: `claude -p --model claude-haiku-5-5 --restricted
--add-dir <scope> --max-turns N --permission-prompts none --output-format json`, Max plan auth, at
power ≥ 4 behind a spoken + tapped confirmation; Keeper-on-Haiku option in the Arm screen.

## Not in v1 (explicitly)

ANE worker (v2), heavy 14B tier in any role, Siri-spoken replies, Watch, LSP, Gemini, sleep/lid
handling, Docker CPU fallback, multi-user, App Store distribution, Headscale, cost-in-dollars.

## Risks carried into implementation

- `DictationTranscriber` Turkish on-device and `AnalysisContext` behaviour are **likely**, not
  certain → M4 starts with a 1-hour spike on device before UI work.
- Background audio for the turn loop is best-effort → v1 runs the loop in the foreground.
- `powermetrics` plist thermal key name unverified → M2 dumps one sample first.
- 3B Keeper deltas may be over-conservative → acceptable because the user approves/edits each one;
  measured in M5.
