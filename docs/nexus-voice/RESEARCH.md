# NEXUS Voice — research findings (2026-10-25)

Scope: facts needed before designing the voice-driven, phone-controlled development assistant
(Arm → Run model, WireGuard transport, local MLX/llama.cpp roles, `claude -p` executor).
Each section ends with the decision the facts support, or the question left for Sertan.
Confidence: **C** verified on this machine or in primary docs today, **L** likely, **U** unverified.

Host: M4 Max, 36 GB, macOS 26.5 (25F5068a), Claude Code 2.1.310, llama-cpp-python 0.3.36 Metal,
mlx-lm 0.32.0. Public IPv4 <public-ipv4>, no IPv6.

---

## 1. Local model roles — measured on the existing tiers

Prompts used Qwen's ChatML template. Timings are server-side `Usage` totals (queue+prefill+decode).

### Listener (intent + repo from one utterance), 12 utterances incl. one Turkish

| Setup | Correct | Median latency | Failure modes |
|---|---:|---:|---|
| MLX 3B, naive prompt, intent+repo+power | 6/10 | 269 ms | markdown fences around JSON; power judgement wrong 2× |
| MLX 3B, intent+repo, no grammar | 6/12 | 173 ms | unquoted JSON value; invented repo (ANE/gRPC_llm) when none named |
| MLX 3B, intent+repo, intent definitions in prompt | **10/12** | 219 ms | "run the tests" → repo gRPC_llm (unnamed); "what did the last run say" → status not summarize |
| llama.cpp 3B Q5, same prompt, hard JSON grammar | 9/12 | 370 ms | same repo-invention, 1 intent miss |

Facts: the Turkish utterance classified correctly every time. The grammar fixes shape, not content. The
remaining misses are "repo not named → model guesses the one it saw in the system prompt".

**Decision.** Listener = MLX 3B with explicit intent definitions, plus two code-side rules that remove the
remaining error classes: (1) repo is taken from the *manifest's active repo* unless the utterance names
another allowed repo (string match), never from the model; (2) power comes from the app control, never
from the model. With those rules the measured error rate is 1/12 and latency ~220 ms.
No model-side JSON grammar is needed; strip fences and parse.

### Reporter (2–3 spoken sentences from session doc + facts)

MLX 3B: 481 prompt tokens → 39 output tokens in **623 ms**, `finish=stop`, no markdown:
"On the NEXUS branch, 32 uncommitted files are ready for the next commit. The team has stabilized the
GPU harness and is now working on chat templating in the service." Only flaw: "the team" instead of
"you" — a prompt fix.

**Decision.** Reporter = MLX 3B. Spoken reply available ~0.6 s after facts are gathered.

### Keeper (update the session document from facts)

| Setup | Result | Time |
|---|---|---:|
| MLX 3B, full rewrite | Copied the old document verbatim, then appended the raw FACTS block, hit the 400-token cap | 2.9 s |
| MLX 3B, structured delta (JSON of done_add / next_replace / open_add) | `done_add: []` although FACTS said "stability harness passed" — safe but useless | 0.6 s |
| 14B llama.cpp, full rewrite | Correct: added the dated done item, flipped plan item to (done), rewrote facts, kept everything else | 8.8 s |
| 14B llama.cpp, structured delta | done_add correct; open_add duplicated existing items and misfiled an event | 3.7 s |
| Haiku 5.5 via `claude -p` (one-word probe, for cost scale) | $0.00085 for 4.1K cache-write + 3.3K cache-read tokens | 1.6 s API, 2.9 s wall |

**Decision.** The 3B cannot keep the document. Two viable Keepers: the 14B at ~9 s *off the spoken path*
(run after the reply, GPU warm for ~10 s per turn, zero cloud tokens), or Haiku at roughly $0.002 per
turn with the full document. v1 picks the 14B so power 1 stays at zero cloud; the Keeper runs
asynchronously after each turn and the Reporter speaks from last turn's document plus fresh facts.
The `facts` section is written by code, not by any model.

---

## 2. Claude Code headless executor (`claude -p`) — C

Verified on 2.1.310 (`claude --help`) and official docs (code.claude.com/docs/en/cli-reference, /headless).

| Need | Flag | Note |
|---|---|---|
| Model, explicit | `--model claude-haiku-5-5 \| claude-sonnet-5-5 \| claude-opus-5-5 \| claude-fable-5-1` | aliases `haiku/sonnet/opus/fable` exist; use full ids so the power table is unambiguous |
| Effort | `--effort low\|medium\|high\|xhigh\|max` | pin `low`/`medium` at power 13 |
| Turn cap | `--max-turns N` | exits with `subtype=error_max_turns` |
| Spend cap | `--max-budget-usd X` | client-side *estimate*, can overshoot; subagents count; leave headroom |
| Scope | `--add-dir <paths>` + `--restricted` | `--restricted` confines file tools to cwd + add-dirs, removes Bash/code tools unless `--tools` names them, refuses bypassPermissions |
| Tools | `--tools "Read,Grep,Glob"` or `--allowedTools "Bash(git *)"` | `--tools ""` disables all |
| Permissions | `--permission-mode plan\|acceptEdits\|dontAsk` + `--permission-prompts none` | `none` auto-denies anything that would prompt |
| Output | `--output-format json` | returns a JSON **array**: `system/init`, `assistant`…, `rate_limit_event`, final `result` |
| Structured | `--json-schema '<schema>'` | adds `structured_output` |
| Sessions | `--session-id <uuid>`, `--resume <id>`, `--no-session-persistence` | `-p` sessions get no title; plain `--continue` skips them |
| Isolation | `--bare` | skips hooks/CLAUDE.md/memory/keychain; **API-key auth only** |

`result` record fields (measured): `total_cost_usd`, `usage` (input/output/cache tokens, `iterations[]`),
`modelUsage{model: {costUSD, contextWindow, …}}`, `num_turns`, `duration_ms`, `duration_api_ms`,
`session_id`, `stop_reason`, `is_error`, `permission_denials`, `result`.

Billing facts that matter for the power table:
- If `ANTHROPIC_API_KEY` is exported, `-p` **always** uses it → per-token API billing. Unset it to draw
  from the Max/Pro plan (rolling 5-hour window + weekly cap, shared with claude.ai).
- `--max-budget-usd` cannot cap plan-window usage; it only bounds the USD estimate.
- `--bare` ignores subscription auth. Don't use `--bare` if the plan is the intended payer.

**Decision.** Executor shells out to `claude -p --output-format json` with: explicit model id, effort,
`--max-turns`, `--max-budget-usd`, `--add-dir` from the manifest, `--restricted` at power 4–5 (read-only),
`--permission-mode acceptEdits --permission-prompts none` at power ≥ 6 after spoken confirmation,
`--session-id` chosen by nexusd so the session is resumable and findable. No Agent SDK in v1 (same
controls, adds a dependency, cannot use plan auth).

**Question.** Plan auth or API key for the executor? Plan = no per-token bill but a shared 5-hour window
the app cannot meter; API key = exact `total_cost_usd` per turn and a hard `--max-budget-usd`. The
joule/dollar ledger in the app is only exact with the API key.

---

## 3. Claude Code session artefacts (fact source for the Keeper) — C on this machine

- Path: `~/.claude/projects/<cwd with non-alphanumerics → '-'>/<session-id>.jsonl`; sidecar dir
  `<session-id>/{subagents,tool-results}`; `memory/` per project; `sessions-index.json`.
- `sessions-index.json` entries: `sessionId, fullPath, firstPrompt, summary, messageCount, created,
  modified, gitBranch, projectPath, isSidechain`. This is the cheapest "what happened in this directory
  lately" source — no model needed.
- Useful JSONL record types seen (1,596 lines in this session): `user`, `assistant`, `ai-title`
  (`aiTitle`), `cost-state` (`totalCostUSD`, `modelUsage` per model, `totalLinesAdded/Removed`),
  `last-prompt`, `system/turn_duration`, `file-history-snapshot`, `queue-operation`.
- **Docs say the format is internal and changes between versions.** Parse defensively: read
  `sessions-index.json` first, then `ai-title`, `cost-state`, `last-prompt`, and the last few `user`
  text blocks; ignore everything else.
- Note: this repo moved; the old path `-Users-<user>-Documents-Software-AI-gRPC-llm` holds the
  history, the new iCloud path has one session. The Keeper must map *both* directory names to one repo.

---

## 4. Power, thermal, utilisation on the Mac — C unless noted

| Signal | Source | Root? | Verified here |
|---|---|---|---|
| CPU/GPU/ANE mW, combined, energy (nJ) | `powermetrics --samplers cpu_power,gpu_power,ane_power -f plist` | **yes** | "must be invoked as the superuser" |
| Thermal pressure (Nominal/Moderate/Heavy/Trapping/Sleeping) | `powermetrics --samplers thermal` | yes | — |
| Thermal state (nominal/fair/serious/critical) | `ProcessInfo.thermalState` + change notification | no | returns 0 (nominal) |
| Thermal warning level | `IOPMGetThermalWarningLevel`, `pmset -g therm` | no | "No thermal warning level recorded" |
| GPU busy % | `ioreg -r -d1 -c IOAccelerator` → `PerformanceStatistics.Device Utilization %` (also Renderer/Tiler %, In-use memory) | no | 53% while MLX served |
| Die temperatures | private `IOHIDEventSystemClient` (macmon, iSMC, Chromium) | no | not tested; private API |
| ANE utilisation | **none exists**; ANE power is the only proxy | — | — |

- Unprivileged energy readers (macmon, mactop, NeoAsitop) read the same IOReport `Energy Model` counters
  powermetrics uses. macmon's README warns that on **macOS 27** those counters stop updating without a
  private entitlement. None is installed here; `IOReportGroupName = "Energy Model"` is visible in ioreg (6 groups).
- Root without typing a password: `SMAppService.daemon` (bundled LaunchDaemon, user approves once in
  System Settings) or a `/Library/LaunchDaemons` plist; or a one-line sudoers rule for `/usr/bin/powermetrics`.
- **There is no user-space GPU clock/power cap on macOS.** MLX exposes memory limits only; llama.cpp
  Metal has no throttle. Levers that exist: Low Power Mode (`pmset -a powermode 1`, ~13.5 W GPU cap on
  M4 Pro per Eclectic Light, L), which model is loaded, batch size, and pausing/duty-cycling work.
- Lid closed on AC without an external display: `sleep 0` and `caffeinate` do **not** stop lid-close
  sleep (L); `sudo pmset -a disablesleep 1` does, at the cost of disabling lid sleep entirely. Current
  AC profile already has `sleep 0`, `tcpkeepalive 1`. Daemon plist should set `ProcessType=Interactive`
  to avoid launchd's background throttling.

**Decision.** Telemetry = a small root helper (LaunchDaemon) that runs `powermetrics -f plist` at 1 s
and publishes samples over a local socket; nexusd (unprivileged) adds `Device Utilization %` from
ioreg and `thermalState`. Joules = ∑(combined mW × interval). The Arm screen shows watts by rail,
accumulated joules, GPU %, thermal state; "ANE %" is not shown because it cannot be measured.
Power *bounding* is implemented as policy, not hardware: the manifest's ceiling decides which tier may
load, and the keeper/executor pause when thermal state ≥ serious or a joule budget is hit.

**Question.** Is `disablesleep 1` acceptable for lid-closed operation (the Mac then never sleeps on
lid close while on AC), or will the Mac stay open/on an external display when remote?

---

## 5. Scope enforcement — C

- `/usr/bin/sandbox-exec` still works on 26.5 (tested by the agent: `(deny default)` + `file-read*`
  subpath allowlist denies `/Users`), but it is marked deprecated since 2017 and SBPL is undocumented.
- Fully supported option: canonicalise (`realpath`, `O_NOFOLLOW`) and prefix-check every path in our
  own fact collectors; this does not protect against a compromised interpreter.
- For the cloud executor, scope is `--add-dir` + `--restricted` (file tools confined to those dirs).

**Decision.** Two layers: our collectors enforce the manifest allowlist in code (portable, supported),
*and* run under a `sandbox-exec` read-only profile generated from the same allowlist as defence in
depth while it keeps working. If `sandbox-exec` disappears, layer one still holds.

---

## 6. Transport — C/L

- No kernel WireGuard on macOS; both the App Store app and Homebrew `wireguard-tools` use
  `wireguard-go` on a `utunN` interface. Neither is installed yet.
- This network: public IPv4 `<public-ipv4>` seen from outside, **not** in `100.64.0.0/10`, no global
  IPv6. Router WAN IP still to be compared (if equal → no CGNAT → WireGuard-direct works with a UDP
  port-forward and dynamic DNS).
- Single-peer hardening: server `AllowedIPs = <phone>/32`, `PersistentKeepalive = 25` on the phone
  (cellular may want 15), `PresharedKey` for the extra symmetric layer, bind nexusd to the utun
  *address* (interface name is dynamic). Static keys do not rotate themselves — rotate on a schedule
  with `wg set`.

**Decision.** WireGuard-direct, pending the router check. Headscale only if CGNAT is confirmed.

---

## 7. iOS client — C unless noted

**Speech to text.**
- iOS 26 introduced `SpeechAnalyzer` / `SpeechTranscriber` / `DictationTranscriber` as the successor
  to `SFSpeechRecognizer`: entirely on-device, models downloaded via `AssetInventory`, **no documented
  duration limit** (SFSpeechRecognizer stops every task at 60 s and is throttled per day for server
  locales). Not available on watchOS.
- Turkish: `tr_TR` appears in third-party `SpeechTranscriber.supportedLocales` dumps (~40 locales) and
  has been on-device for `SFSpeechRecognizer` since iOS 13 (L). Confirm at runtime; no Apple page lists it.
- Custom vocabulary: `AnalysisContext.contextualStrings` is documented for **DictationTranscriber**
  (and `SFSpeechLanguageModel` via `ContentHint.customizedLanguage`); SpeechTranscriber's page does
  not mention it and third parties report it ignores them (L). Legacy `contextualStrings`: max 100
  phrases, 1–2 words each.
- Background: continuous capture needs `UIBackgroundModes: audio` and an active `.playAndRecord`
  session before backgrounding; shows the status-bar indicator; App Review scrutinises it. Audio-ML in
  the background has broken across releases (iOS 18 SoundAnalysis). Test on device early.

**Text to speech.** `AVSpeechSynthesizer` is fully on-device; enhanced/premium voices must be
downloaded by the user in Settings (no API to trigger or list them); iOS 26.0–26.1 bug: select voices
by identifier, not language (L).

**Siri / App Intents.**
- Invocation phrases must include the app name and cannot carry a free-text `String` parameter; only
  `AppEnum`/`AppEntity` values interpolate. So **"Hey Siri, ask NEXUS <anything>" in one step is
  impossible**; the supported shape is "Hey Siri, ask NEXUS" → Siri asks "What?" → you speak → the
  intent runs. `ProvidesDialog` lets Siri *speak* the intent's reply.
- Locked phone: a **background** intent with `authenticationPolicy = .alwaysAllowed` runs while
  locked; anything that foregrounds the app forces an unlock. iOS 26 `supportedModes` replaces
  `openAppWhenRun` (L).

**WireGuard.**
- Embedding (`WireGuardKit` + `NEPacketTunnelProvider`) needs the Network Extension entitlement, an
  App Group, and a **paid Developer Program membership** (not available to free personal teams). No
  Apple approval step. Own tunnel can be started from an App Intent (NetBird does this, L).
- The official WireGuard app has On-Demand rules but **no Shortcuts/App Intents**; the generic
  Shortcuts "Set VPN" action (iOS 16.4+) can toggle its profile.
- An app can only start/stop *its own* tunnel, never another app's.

**SSE in Swift.** `URLSession.bytes(for:)` streams the body; no first-party EventSource. Gotchas:
`timeoutIntervalForRequest` (60 s) is an *idle* timeout → server heartbeats < 30 s; `.lines` drops the
empty lines that delimit SSE events → parse raw bytes; no auto-reconnect; the stream dies on app
suspension; background `URLSession` cannot stream.

**Watch.** `WCSession.sendMessage` from the Watch wakes the iPhone app in the background; the Watch
has no Speech framework, so it sends dictated *text* via the system text-input controller and can
speak the reply with `AVSpeechSynthesizer`. Payload ~65 KB (U).

**Decisions.**
- STT = `DictationTranscriber` with `AnalysisContext` vocabulary (repo names, tier names, "NEXUS"),
  iOS 26 only; no SFSpeechRecognizer fallback, which removes the 60-second restart dance.
- Two entry paths, one backend: (1) **Siri background intent** "ask NEXUS" → Siri collects the
  question → `/turn` → Siri speaks the reply — works locked, from the pocket, no app UI; (2) **the app**
  for the conversational loop and the Arm screen. The turn loop runs in the foreground with the audio
  background mode as a best-effort extension, not a promise.
- Tunnel: **embed WireGuardKit** so "Hey Siri, ask NEXUS" can bring the tunnel up itself. Requires the
  paid developer account; sideloaded via Xcode, never App Store, so TN3120's "genuine VPN" rule does
  not apply.
- Watch: v2, text-only relay.

---

## 8. Gemini as a second medium / research executor — C

- Live API native-audio models return **audio only**; text comes via the `output_audio_transcription`
  side channel. A pure STT front end exists: `gemini-3.5-transcribe-live` over the same WebSocket with
  `response_modalities=["TEXT"]`, Turkish supported, 10-minute sessions, ~$0.009/audio-minute.
- Deep Research agents (`deep-research-preview-04-2026`, `-max-`) are API-only via the Interactions
  API, async (`background=True`), ~$1–3 per task standard, ~$3–7 max.
- Gemini CLI has a headless mode comparable to `claude -p` (`gemini -p`, `-o json`, `--include-directories`,
  `--approval-mode`), but it was replaced by "Antigravity CLI" for free tiers in June 2026 and is not
  tuned for Gemini 4 — support is uncertain.

**Decision.** Gemini enters as a *research executor* (Deep Research via API, writing into the session
document through the Keeper) — not as a voice front end in v1, since Apple's on-device speech is free
and private. Gemini CLI is not a dependency.

---

## 9. Manifest (the data lockstep) — draft schema

```json
{
  "manifest_version": 1,
  "session_id": "uuid",
  "created": "2026-10-25T03:10:00-04:00",
  "repo": {"name": "gRPC_llm", "root": "/Users/…/gRPC_llm",
           "claude_project_dirs": ["-Users-…-Software-AI-gRPC-llm", "-Users-…-Documents---Sertan-s-MacBook-Pro-Software-AI-gRPC-llm"]},
  "scope": [{"path": "/Users/…/gRPC_llm", "mode": "read"},
            {"path": "/Users/…/gRPC_llm/docs", "mode": "read+write"}],
  "engine": {"tiers_allowed": ["standard-mlx", "heavy"], "idle_stop_s": 300,
             "keeper": "heavy", "listener": "standard-mlx", "reporter": "standard-mlx"},
  "power": {"ceiling": 6, "default": 1,
            "cloud": {"4": "claude-haiku-5-5", "6": "claude-sonnet-5-5", "8": "claude-opus-5-5", "13": "claude-fable-5-1"},
            "max_turns": 8, "max_budget_usd_per_call": 0.50, "daily_budget_usd": 5.00},
  "limits": {"pause_on_thermal_state": "serious", "joule_budget": 200000, "max_gpu_watts_warn": 25},
  "loop": {"silence_timeout_s": 20, "end_words": ["done", "bitti"], "confirm_mode": "spoken",
           "reply_sentences": 3, "locale": "en-US"},
  "hash": "sha256 of the canonical JSON above"
}
```

The Mac composes it; the app displays it and the user approves; both store `hash`; every `/turn`
carries it; nexusd refuses a turn whose hash differs from the armed one.

## 10. Arm screen — field list derived from the above

Inventory (read-only): CPU/GPU/ANE watts (if helper running), GPU %, thermal state, memory free,
disk free, tiers present/loaded, Docker running, WireGuard peer latency.
Scope: directory tree rooted at allowed roots; per-entry read / read+write toggle.
Engine: tier checkboxes, idle-stop, role→tier assignment (defaults from §1).
Power: ceiling slider 1–13 with the model name shown at each step, per-call and daily USD caps,
auth mode (plan / API key) with the metering caveat from §2.
Limits: thermal pause threshold, joule budget, GPU-watts warning.
Loop: silence timeout, end words, confirm mode, reply length, locale.
Lockstep: manifest preview + hash, Approve.

## 11. Decisions taken 2026-10-25 (Sertan)

| Topic | Decision |
|---|---|
| Executor auth | **Max plan only.** No `ANTHROPIC_API_KEY`, no Agent SDK. Metering in the app = turns and tokens from the `result` JSON, labelled as plan-window usage, not dollars. Caps = `--max-turns` per call and a daily turn count. |
| Keeper | **3B with expert control.** The 3B proposes a structured delta; the app shows it; the user approves or edits before code applies it. Haiku is the Keeper at higher power / when the user enables it in the Arm screen. |
| Listener | 3B accuracy is acceptable because intents are **verified, not fired**: rulesets and the HMI carry repo and power; the model only proposes intent, and the app confirms anything non-trivial. |
| Rulesets vs inference | Deterministic layers first (keyword grammar, path allowlist, power from the app control); inference only where text must be understood or produced. |
| Telemetry | Apple-only LaunchDaemon helper for `powermetrics` is acceptable for now; it is a platform module, and the HMI shows exactly what is measured (no ANE %). |
| Sleep / lid | Out of v1. A separate suite later. |
| Apple Developer | Paid membership available → **embedded WireGuardKit tunnel** in the app. |
| Siri | v1: "Hey Siri, open NEXUS" App Shortcut that launches the app; the app connects. Siri-spoken replies deferred. |
| iOS | **iOS 26 only** (SpeechAnalyzer / DictationTranscriber). |
| Transport | WireGuard-direct; router WAN is fine for v1. |
| Credentials, on-device locales | To be learned from user tests, not assumed. |

## 12. Open questions (resolved or deferred)

1. Executor auth: plan (unmetered) or API key (exact metering)? — §2
2. `disablesleep 1` for lid-closed operation? — §4
3. Router WAN IP equals <public-ipv4>? — §6
4. Keeper on the 14B (zero cloud, ~9 s async, GPU warm per turn) or Haiku (~$0.002/turn, GPU cold)? — §1
5. Paid Apple Developer Program membership available? It gates the embedded tunnel. — §7
6. Siri's two-step "ask NEXUS → What? → question" acceptable as the hands-free path, given the one-step
   form cannot exist? — §7
7. iOS 26-only app (SpeechAnalyzer) — fine? — §7
