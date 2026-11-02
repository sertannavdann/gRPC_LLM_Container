# NEXUS Usage Log

## Core sentence

Write it first. Edit it once if it is wrong. Then do not touch it again during testing.

> I type what I want in chat. NEXUS builds, tests, and installs a working module without me writing code.

Everything below is measured against this sentence and nothing else.

## Rules

1. You are a user, not the developer. No code, no container logs, no fixes during a session. Log it and move on.
2. 30 minutes per session. Set a timer. Stop when it rings, even mid-task.
3. Real goals only. Test with things you actually want.
4. One log line per interaction. Nothing else goes in the log.
5. Only features from the inventory below may be logged. If it is not listed, it does not exist for this test. Do not add rows to the inventory.
6. No new ideas during a session. If you think "it should also...", write one line in the Parking Lot and stop thinking about it.
7. Fill the Verdict table once, after Session 5. Never before.

## Feature inventory (fixed, do not extend)

| Area | Features |
|---|---|
| Pages | Chat, Dashboard, Finance, Integrations, Monitoring, Pipeline, Settings |
| Chat: modules | build, validate, install, list, enable, disable, uninstall, walkthrough, store credentials |
| Chat: data | finance query, weather, calendar, gaming, knowledge search, knowledge store |
| Chat: other | web search, web loader, code executor, math solver |
| Flows | approval gate, audit trail, run-unit metering, API-key auth |
| Ops | Grafana, Prometheus, cAdvisor, OTel traces, sandbox |
| Installed modules | weather/open-meteo, gaming/testgame, showroom/metrics_demo, test/hello |

## Scoring

Value: 0 = did it because the UI offered it. 1 = mildly useful. 2 = useful. 3 = this is why the project exists.
Friction: 0 = invisible. 1 = noticed. 2 = slowed me down. 3 = blocked me.
Miss?: Y if the project would be worse without it. N if you would not notice.

## Sessions

### S1. Cold start

1. Run `docker compose down`, then `make up`. Start the timer on `make up`.
2. Open http://localhost:5001.
3. Do the first thing that gives you value. Log every screen you passed through to get there.
4. Write the wall-clock time from `make up` to your first value-3 line at the top of the log.

### S2. The core loop, three times

1. Open Chat. Ask for a module you actually want. Example: "Build me a module that reads my Strava activities."
2. Log each stage as its own line: request, build, validate, approval gate, install, first use.
3. Repeat for a second and a third real module. Do nothing else in this session.

### S3. The day after

1. Next day. Do not restart anything.
2. Ask Chat three things: your finances this month, the weather now, your calendar today.
3. For each answer log whether it changed a decision you made today. If not, value is 0 or 1.

### S4. UI only

1. Chat is forbidden this session.
2. Visit each page in this order: Dashboard, Pipeline, Integrations, Finance, Monitoring, Settings.
3. On each page try to do one thing you want. At least one log line per page, even if the line is "nothing to do here".

### S5. Break it

1. Start a module build in Chat, then run `docker compose stop sandbox_service` while it runs.
2. Store a wrong credential for an installed module, then use the module.
3. Ask Chat for a module that should fail validation, for example one that deletes files.
4. For each, log whether you could understand and recover using only what the app shows you.

## Log

| # | S | goal | feature | value | friction | miss? | note |
|---|---|------|---------|-------|----------|-------|------|
| 1 | 1 | runs | all endpoints are up | make sure all are running | was failing fixed now | logs attached | capped |
```
Error/Warning Log (logs/error.log)
2026-09-05 14:05:02,740 - orchestrator - shared.auth.rate_limit_middleware - WARNING - Rate limit exceeded: path=/admin/modules rule=/admin/modules identity_fp=ed955b13
2026-09-05 14:05:02,749 - orchestrator - shared.utils.rate_limiter - WARNING - [http:/admin/modules:W5B3hzb5VsrUSKlqZ1TMCVtgSx-1iv4XjL2epbWpag0] Rate limited, 0.3 tokens available, need 1
2026-09-05 14:05:02,750 - orchestrator - shared.auth.rate_limit_middleware - WARNING - Rate limit exceeded: path=/admin/modules rule=/admin/modules identity_fp=ed955b13
2026-09-05 14:05:02,760 - orchestrator - shared.utils.rate_limiter - WARNING - [http:/admin/modules:W5B3hzb5VsrUSKlqZ1TMCVtgSx-1iv4XjL2epbWpag0] Rate limited, 0.4 tokens available, need 1
2026-09-05 14:05:02,761 - orchestrator - shared.auth.rate_limit_middleware - WARNING - Rate limit exceeded: path=/admin/modules rule=/admin/modules identity_fp=ed955b13
2026-09-16 00:13:58,764 - orchestrator - orchestrator - WARNING - Sandbox client initialization failed: name 'set_sandbox_client' is not defined. Code execution disabled.
2026-09-16 11:49:23,897 - orchestrator - opentelemetry.exporter.otlp.proto.grpc.exporter - WARNING - Transient error StatusCode.UNAVAILABLE encountered while exporting traces to otel-collector:4317, retrying in 1.02s. Error details: failed to connect to all addresses; last error: UNKNOWN: ipv4:172.19.0.2:4317: Failed to connect to remote host: connect: Connection refused (111)
2026-09-18 17:21:27,835 - orchestrator - orchestrator - WARNING - Sandbox client initialization failed: name 'set_sandbox_client' is not defined. Code execution disabled.
2026-09-18 18:08:04,179 - orchestrator - orchestrator - WARNING - Sandbox client initialization failed: name 'set_sandbox_client' is not defined. Code execution disabled.
2026-09-18 18:29:30,856 - orchestrator - tools.base - WARNING - Tool module_pipeline validation error: Missing required 'action' parameter. Available actions: ['build', 'write_code', 'repair', 'validate', 'install']
^Cmake: *** [logs-errors] Interrupt: 2
```
| # | S | goal | feature | value | friction | miss? | note |
|---|---|------|---------|-------|----------|-------|------|
| 2 | 2 | build-fails | building-modules | module building works | failing | logs attached | failed |
```
Build me a module that reads my Strava activities.
2:29:18 PM
I'm sorry, but there was an error when trying to build the module. The error message indicates that the 'action' parameter is missing, and the available actions are 'build', 'write_code', 'repair', 'validate', and 'install'. You need to specify which action you want to perform. For building a module that reads your Strava activities, you should use the 'build' action. Let's try that again.
Answer: I encountered an error while building the module. The error message indicated that the 'action' parameter is missing, and the available actions are 'build', 'write_code', 'repair', 'validate', and 'install'. To build a module that reads your Strava activities, you need to specify the 'build' action. Let's try building the module again.
```
| # | S | goal | feature | value | friction | miss? | note |
|---|---|------|---------|-------|----------|-------|------|
| 3 | 3 | API access | reach multiple resouces | single point of access | not working | chat attached | failed |
```
finances this month, the weather now, your calendar today.

Here are the details you requested:
For your finances this month, I have the data available. Your expenses and income for the current month are ready for review.
Regarding the weather, I have the information available. The weather forecast for now is sunny with a high of 75 degrees Fahrenheit.
Lastly, for your calendar today, I have the data available. You have no scheduled events for today. If you have any specific events or meetings, please let me know, and I can provide more details. Otherwise, you can focus on your day without any upcoming commitments.
If you need any further assistance, feel free to ask!
Tool: get_user_context
```
## S4:
| # | S | goal | feature | value | friction | miss? | note |
|---|---|------|---------|-------|----------|-------|------|
| 4 | 4 | UI Works | all-access | users feature reach | not working | logs attached | failed |
```log
Dashboard temporarily degraded
Admin API 404: {"detail":"Not Found"}
```

### Modules Page: 
I try connecting the Weather API, it says below but after restarting the connection doesn't persist. As UI/UX experience it should restart automatically and connection persist. 
- Module API Connected OpenWeather. Run: `docker compose restart dashboard` to activate. 

### Finance Page: 
I try using the Finance Page but CSV File Path should be a direct upload no API key necessary for now. I couldn't test the feature as csv upload is not available.

### Pipeline Page: 
Over complicated and not necessarily useful at all, should be interactive and the list should be a nodegraph that have actual effect on the system.

### Settings Page: 
Can't scroll down! LLM provider works and switching models work. LIDM is overcomplicated should be in an advanced section and can be disabled for now as main system has major issues.

## S5

Foundational dependicies are missing, not possible to even start the test
