# Agentic Flow Patterns for NEXUS Module Builder: soul.md, Auto-Prompts, and Orchestrated Agent Roles

## 1. The Agentic Code Generation Paradigm

The shift from single-pass LLM code generation to **multi-agent agentic flows** represents a fundamental paradigm change validated by extensive academic research. A comprehensive survey of 447 papers (Dong et al., Peking University, 2025) identifies three core properties that distinguish agent-based code generation from traditional LLM calls:[^1]

1. **Autonomy** — agents independently manage the workflow from task decomposition to coding and debugging
2. **Expanded task scope** — capabilities extend beyond code snippets to encompass the full software development lifecycle
3. **Engineering practicality** — emphasis shifts from algorithmic innovation toward system reliability, process management, and tool integration

This maps directly to your NEXUS Phase 3 self-evolution engine: instead of treating the LLM Gateway as a dumb code-generation endpoint, you wrap it with specialized agent personas (Builder, Tester, Critic) that each carry their own `soul.md` — a structured identity document that defines their role, constraints, acceptable patterns, and output contracts.

## 2. Multi-Agent Workflow Taxonomies (Academic Foundation)

### 2.1 Four Canonical Workflow Types

The Peking University survey classifies multi-agent code generation systems into four workflow architectures:[^1]

| Workflow Type | Description | Academic Examples | NEXUS Mapping |
|---|---|---|---|
| **Pipeline-based Labor Division** | Sequential stages where each agent handles a specific SDLC phase | AgentCoder (programmer → test designer → executor), Self-Collaboration (analysis → coding → testing) | Builder Agent → Tester Agent → Validator |
| **Hierarchical Planning-Execution** | Higher-level agents decompose tasks; lower-level agents execute | PairCoder (Navigator plans, Driver implements), MetaGPT (PM → Architect → Engineer → QA) | Build Orchestrator → Builder/Tester sub-agents |
| **Self-Negotiation Circular Optimization** | Agents negotiate, reflect, iterate through feedback loops | CodeCoR (4 agents: prompts, code, tests, repair), MapCoder (recall → plan → code → debug) | Repair loop with validator feedback |
| **Self-Evolving Structural Updates** | Systems dynamically adjust structure based on effectiveness | SEW (workflow self-evolution), EvoMAC (text backpropagation) | Future: adaptive pipeline reconfiguration |

### 2.2 Role-Playing as a First-Class Mechanism

Academic literature explicitly validates **role-playing** as a critical mechanism in multi-agent code generation:[^1]

> "Role-playing refers to adding specific identity settings in prompts, such as programmers, testers, project managers, or code reviewers. This mechanism makes agent behavior more consistent with corresponding role responsibilities and thinking patterns. The system designs corresponding prompt strategies for each role, enabling them to perform their duties in collaboration."

This is precisely the `soul.md` pattern — each agent's system prompt contains its role definition, acceptable patterns, output format requirements, and decision boundaries.

## 3. The soul.md Pattern: Defining Agent Identity

### 3.1 Concept and Origin

The `soul.md` pattern (also called **Agent Charter**, **Role Definition**, or **Mode Definition**) is a structured identity document that configures an LLM agent's behavior at the system prompt level. The pattern has been formalized in several production systems:[^2][^3]

- **Roo Code** uses `.mode.md` files with TOML+Markdown that define `roleDefinition`, `customInstructions`, `allowedTools`, and `fileRestrictions`
- **Kiro (AWS)** uses `requirements.md`, `design.md`, and `tasks.md` as specification-driven contracts
- **CrewAI** configures each agent with a `role`, `goal`, `backstory/persona`, and tool set[^4]

The common structure across all implementations:[^5][^2]

```
soul.md structure:
├── Mission          — target outcome and success metric
├── Scope            — allowed code paths and boundaries
├── Capabilities     — planning, tool use, critique, tests
├── Guardrails       — secrets policy, file boundaries, constraints
├── Interfaces       — input/output contracts
├── Metrics          — quality measures (pass rate, coverage)
├── Stop Conditions  — failure thresholds, max iterations
└── Acceptable Patterns — coding standards, architectural rules
```

### 3.2 Why soul.md Works (The Persona Pattern)

The **Persona Pattern** in prompt engineering leverages the LLM's training data to activate domain-specific reasoning without exhaustive instructions:[^6]

- **Prompt Efficiency** — a concise role invocation condenses complex instructions
- **Emergent Capabilities** — personas tap into internalized methodologies not explicitly detailed in the prompt
- **Natural Reasoning** — responses mirror human-like role-specific thinking patterns
- **Adaptive Learning** — as models improve, persona depth evolves automatically

## 4. The Planner-Coder Gap: Critical Problem to Solve

### 4.1 Academic Evidence

A rigorous empirical study (arXiv:2510.10460, 2025) reveals a fundamental flaw in multi-agent code generation: the **planner-coder gap**, which accounts for **75.3% of all robustness failures** in multi-agent systems:[^7]

> "This gap arises from information loss in the multi-stage transformation process where planning agents decompose requirements into underspecified plans, and coding agents subsequently misinterpret intricate logic during code generation."

Semantically equivalent inputs caused MASs to fail on **7.9%–83.3%** of problems they initially solved correctly.[^7]

### 4.2 Mitigation Strategy

The researchers propose a **repairing method** that solves 40%–88.9% of identified failures through:[^7]

1. **Multi-prompt generation** — generate multiple candidate plans/implementations to reduce information loss
2. **Monitor agent** — introduce a dedicated agent that bridges the planner-coder gap by validating plan fidelity during execution

For NEXUS, this means your Build Orchestrator should not simply pass a single plan from scaffold to implement. Instead:

- Generate 2-3 scaffold candidates and score them against the intent
- Insert a **Monitor** check between scaffold and implement that validates the implementation matches the scaffold's assumptions
- Feed the `assumptions` and `rationale` fields from your builder contract back into the Tester agent's context

## 5. Concrete Agent Definitions for NEXUS

### 5.1 Builder Agent soul.md

Based on the AgentCoder pipeline pattern (programmer → test designer → executor) and the Agent Charter framework:[^5][^1]

```markdown
# Builder Agent — soul.md

## Mission
Transform natural-language module intent into schema-valid patch payloads
that pass policy validation and sandbox execution.

## Role Definition
You are a senior module engineer for the NEXUS platform. You generate
adapter modules as patch-based file changes (`changed_files`). You think
in terms of bounded contexts, contract-first design, and defensive coding.

## Scope
- ONLY generate files within allowlisted paths
- ONLY use approved imports (see policy profile)
- NEVER include markdown fences in file content
- NEVER generate files outside the module boundary

## Capabilities
- Stage: scaffold | implement | repair
- Output: structured JSON matching BuilderGenerationContract
- Tools: policy_check, schema_validate, dependency_resolve

## Output Contract (Required Fields)
- stage, module, changed_files, deleted_files
- assumptions, rationale, policy, validation_report

## Acceptable Patterns
- REST client via approved HTTP library only
- OAuth flows via platform credential manager
- Pagination with loop guards (max_pages + cursor dedup)
- Error classification: AUTH_INVALID | AUTH_EXPIRED | TRANSIENT | FATAL
- Rate limiting: respect 429 + Retry-After header

## Guardrails
- No dynamic imports, exec(), eval(), or subprocess
- No network calls outside integration mode allowlist
- File count bounded to N per attempt
- Total patch size bounded to M bytes

## Stop Conditions
- Schema validation failure → reject immediately
- Policy violation → reject immediately
- 3 consecutive identical error fingerprints → escalate
```

### 5.2 Tester Agent soul.md

Based on the CodeCoR reflection-scoring pattern and Blueprint2Code's debugging agent:[^8][^1]

```markdown
# Tester Agent — soul.md

## Mission
Validate generated modules through contract tests (Class A) and
feature-specific tests (Class B) to produce attestable ValidationReports.

## Role Definition
You are a QA engineer who writes deterministic, reproducible test suites.
You think adversarially — your job is to find failures, edge cases, and
contract violations. You never assume generated code is correct.

## Scope
- Generate test files ONLY within the test directory
- Test ONLY the public interface of the generated module
- NEVER modify the module source code

## Capabilities
- Stage: test_generation | test_execution | repair_hints
- Output: structured JSON matching TestSuiteContract
- Tools: sandbox_exec, schema_validate, coverage_report

## Test Taxonomy
### Class A — Generic Contract Tests (host-side, fast)
- A1: Registration contract (module registers correctly)
- A2: Interface contract (exports match declared capability)
- A3: Schema contract (output matches canonical adapter envelope)
- A4: Error handling contract (errors use standardized codes)
- A5: Config/credential contract (secrets not leaked)

### Class B — Feature-Specific Tests (sandbox runtime)
- B1: Connectivity (target API reachable in integration mode)
- B2: Authentication (valid/invalid/expired credential paths)
- B3: Data mapping (input→output transformation correctness)
- B4: Visualization rendering (chart artifacts valid)
- B5: Orchestrator integration (round-trip message flow)
- B6: Dev-mode reload safety (hot-reload doesn't corrupt state)

## Quality Gate
### Hard Gate (ALL must pass for VALIDATED)
- All A1–A5 pass
- Required B-suite for declared capability passes
- Zero security violations

### Soft Gate (advisory, tracked)
- Coverage >= 80%
- B5 orchestrator round-trip pass
- B6 dev-mode safety pass

## Repair Hint Protocol
When tests fail, produce structured hints:
- failed_test_id, failure_category, suggested_fix, confidence
Feed these to Builder Agent's repair stage.

## Stop Conditions
- All hard gate tests pass → emit VALIDATED status
- Hard gate failure after max attempts → emit FAILED with report
```

## 6. Orchestrator Auto-Prompt Flow

### 6.1 Architecture Pattern: Orchestrator-Workers with Evaluator Loop

Anthropic's production agent research identifies the **Orchestrator-Workers** pattern as ideal when "you can't predict the subtasks needed" and the **Evaluator-Optimizer** pattern for iterative refinement loops. Your NEXUS build pipeline combines both:[^9]

```
Build API (NL intent + constraints + idempotency key)
    │
    ▼
┌─────────────────────────────────────┐
│         BUILD ORCHESTRATOR          │
│   (Saga coordinator + state mgr)   │
│                                     │
│  ┌─ Stage 1: SCAFFOLD ───────────┐  │
│  │  Load: builder.soul.md        │  │
│  │  Auto-prompt: intent → plan   │  │
│  │  Monitor: plan fidelity check │  │
│  └───────────────────────────────┘  │
│              │                       │
│  ┌─ Stage 2: IMPLEMENT ──────────┐  │
│  │  Load: builder.soul.md        │  │
│  │  Auto-prompt: plan → patches  │  │
│  │  Policy Engine: gate check    │  │
│  └───────────────────────────────┘  │
│              │                       │
│  ┌─ Stage 3: TEST ───────────────┐  │
│  │  Load: tester.soul.md         │  │
│  │  Auto-prompt: patches → tests │  │
│  │  Sandbox: isolated execution  │  │
│  └───────────────────────────────┘  │
│              │                       │
│  ┌─ Stage 4: REPAIR (loop) ─────┐  │
│  │  Load: builder.soul.md        │  │
│  │  Input: repair hints + logs   │  │
│  │  Max: 10 attempts             │  │
│  │  Exit: VALIDATED or FAILED    │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
```

### 6.2 Auto-Prompt Construction

The orchestrator dynamically constructs prompts for each agent by composing:[^9][^5]

1. **soul.md** (static) — the agent's identity, loaded from version-controlled files
2. **Stage context** (dynamic) — current stage name, attempt number, prior artifacts
3. **Intent envelope** (from user) — the NL request, constraints, target capability
4. **Repair context** (conditional) — previous failure logs, test hints, validator feedback
5. **Policy constraints** (from Policy Engine) — current allowed imports, path restrictions

```
auto_prompt = compose(
    system = load(f"agents/{agent_role}/soul.md"),
    context = {
        "stage": current_stage,
        "attempt": attempt_number,
        "intent": build_request.intent,
        "constraints": build_request.constraints,
        "prior_artifacts": artifact_store.get_latest(build_id),
        "repair_hints": validator.get_hints(build_id) if stage == "repair",
        "policy_profile": policy_engine.get_profile(build_request.module_type)
    },
    output_schema = load(f"contracts/{stage}_output.json")
)
```

### 6.3 Structured Output Enforcement

Academic research confirms that schema-constrained outputs dramatically improve reliability. The GitHub Models API's `response_format` with JSON schema forces the LLM to produce outputs matching your builder generation contract. This eliminates the need for fragile regex parsing and ensures every response contains all required fields.[^8][^1]

## 7. Blueprint2Code: A Validated Four-Agent Pipeline

The **Blueprint2Code** framework (Mao et al., 2025, PMC) provides strong empirical validation for exactly the pattern you're building:[^8]

| Agent | Role | NEXUS Equivalent |
|---|---|---|
| **Previewing Agent** | Analyzes task complexity, extracts key requirements | Intent Parser (Build API preprocessing) |
| **Blueprint Agent** | Generates hierarchical solution plans, scores them via confidence mechanism | Builder Agent (scaffold stage) |
| **Coding Agent** | Implements the plan following strict conventions, auto-verifies against examples | Builder Agent (implement stage) |
| **Debugging Agent** | Iteratively refines code using test-driven feedback | Builder Agent (repair stage) + Tester Agent |

Key findings from Blueprint2Code experiments:[^8]

- The multi-agent architecture **maintains strong performance even with smaller/weaker models**, because inter-agent collaboration compensates for individual model limitations
- **High-quality blueprint planning reduces debugging iterations** — investing in the scaffold stage pays off exponentially downstream
- The **confidence-based evaluation mechanism** for scoring blueprints across five dimensions (completeness, feasibility, edge-case handling, efficiency, overall quality) improves plan selection controllability

## 8. Self-Correcting Pipeline: Empirical Results

A production-tested self-correcting code generation pipeline (deepsense.ai, 2025) using the smolagents framework demonstrates the value of the iterative agent loop:[^10]

- **Baseline (single LLM request)**: 53.8% success rate
- **With iterative code review + unit test agent loop**: **81.8% success rate**
- The agent uses `max_steps=10` (matching your bounded 10-attempt repair loop)
- Two key tools: **Code Reviewer** (provides human-like quality overview) and **Unit Test Runner** (validates correctness)

This validates your architecture's core assumption: bounded self-repair with structured feedback dramatically improves output quality.

## 9. Bridging the Gap: Monitor Agent Pattern

To address the planner-coder gap (75.3% of multi-agent failures), insert a lightweight **Monitor Agent** between stages:[^7]

```markdown
# Monitor Agent — soul.md

## Mission
Validate fidelity between stages. Ensure the implement stage
faithfully reflects the scaffold plan, and the test stage covers
the implement's actual behavior.

## Checks
- scaffold → implement: Do changed_files match planned files?
  Do assumptions carry through? Are new assumptions documented?
- implement → test: Do tests cover all declared capabilities?
  Do error paths match the module's error classification?

## Output
- fidelity_score (0-100)
- gaps[] (what was planned but not implemented / tested)
- recommendation: PROCEED | REVISE_PLAN | REVISE_IMPLEMENTATION
```

## 10. Key Academic References for This Pattern

1. **Dong, Y. et al.** (2025). "A Survey on Code Generation with LLM-based Agents." Peking University, arXiv:2508.00083. — Comprehensive taxonomy of 100 papers covering single-agent and multi-agent code generation workflows, role-playing mechanisms, and collaborative optimization.[^1]

2. **Mao, K. et al.** (2025). "Blueprint2Code: A Multi-Agent Pipeline for Reliable Code Generation." PMC. — Four-agent framework (Preview → Blueprint → Code → Debug) with confidence-based plan scoring, validated on HumanEval, MBPP, and APPS benchmarks.[^8]

3. **Anthropic Research** (2024). "Building Effective Agents." — Production patterns for agentic systems: prompt chaining, routing, parallelization, orchestrator-workers, and evaluator-optimizer.[^9]

4. **Wang, S. et al.** (2025). "Testing and Enhancing Multi-Agent Systems for Robust Code Generation." arXiv:2510.10460. — Identifies the planner-coder gap (75.3% of failures) and proposes monitor agent + multi-prompt mitigation.[^7]

5. **Nazar, T.** (2025). "The Persona Pattern: Unlocking Modular Intelligence in AI Agents." Towards AI. — Formal analysis of why role-based prompting improves agent behavior through emergent capabilities and natural reasoning.[^6]

6. **Park, D. et al.** (2026). "A Self-Correcting Multi-Agent LLM Framework." Nature. — MCP-SIM framework demonstrating memory-coordinated, physics-aware multi-agent self-correction.[^11]

7. **deepsense.ai** (2025). "Self-Correcting Code Generation Using Multi-Step Agent." — Empirical validation showing iterative agent loops improve success rate from 53.8% to 81.8%.[^10]

8. **Roo Code Documentation** (2025–2026). "Custom Modes." — Production-grade pattern for `.mode.md` agent identity files with role definitions, tool restrictions, and file boundaries.[^3][^2]

## 11. Implementation Recommendations for NEXUS

Based on the combined academic and production evidence:

- **Store soul.md files in version control** alongside your module contracts. Each agent's identity is a versioned artifact, not a hardcoded string. This follows the spec-driven development pattern validated by Kiro and GitHub Spec Kit.[^12]

- **Compose auto-prompts at runtime** by merging the static soul.md with dynamic stage context, intent, and repair hints. Never let the agent see unscoped context — the soul.md's guardrails and scope sections act as architectural boundaries.[^5]

- **Use the Pipeline-based Labor Division** pattern as your primary workflow, with the **Self-Negotiation Circular Optimization** pattern active only during the repair loop. This keeps the happy path fast and predictable while allowing iterative refinement when needed.[^1]

- **Score blueprints before implementation** using the confidence mechanism from Blueprint2Code (completeness, feasibility, edge-case handling, efficiency, quality). Reject low-confidence scaffolds early rather than discovering problems in the test stage.[^8]

- **Insert the Monitor Agent** at stage boundaries to catch the planner-coder gap before it cascades. The 75.3% failure rate from this gap is too high to ignore in a production system.[^7]

- **Enforce structured JSON output schemas** at the LLM Gateway level. Every agent response must match its contract schema before the orchestrator accepts it. This is the single most impactful reliability improvement for agentic code generation.[^9][^1]

---

## References

1. [A Survey on Code Generation with LLM-based Agents](https://arxiv.org/html/2508.00083v1) - They are capable of simulating the complete workflow of human programmers, including analyzing requi...

2. [Custom Modes | Roo Code Docs](https://docs.roocode.com/advanced-usage/custom-modes/) - Roo Code allows you to create custom modes to tailor Roo's behavior to specific tasks or workflows. ...

3. [Customizing Modes | Roo Code Documentation](https://docs.roocode.com/features/custom-modes) - Roo Code allows you to create custom modes to tailor Roo's behavior to specific tasks or workflows. ...

4. [PDF Navigating LLM Agents and Orchestration: A Practical Guide for Developers](https://humanspark.ai/wp-content/uploads/2025/06/Navigating-LLM-Agents-and-Orchestration_-A-Practical-Guide-for-Developers.pdf)

5. [Mastering Agentic Prompting, The New Language for ...](https://margabagus.com/mastering-agentic-prompting-code-generation-2025/) - Agentic prompting for complex code generation in 2025, write charters, declare tools with MCP, use L...

6. [The Persona Pattern: Unlocking Modular Intelligence in AI ...](https://towardsai.net/p/artificial-intelligence/the-persona-pattern-unlocking-modular-intelligence-in-ai-agents) - Personas tap into the LLM's inherent abilities, often producing outputs that encompass methodologies...

7. [Testing and Enhancing Multi-Agent Systems for Robust Code Generation](https://arxiv.org/abs/2510.10460) - Multi-agent systems (MASs) have emerged as a promising paradigm for automated code generation, demon...

8. [Blueprint2Code: a multi-agent pipeline for reliable code ... - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12575318/) - by K Mao · 2025 · Cited by 1 — Automated code generation is a pivotal area within computer science, ...

9. [Building Effective AI Agents](https://www.anthropic.com/research/building-effective-agents) - In this section, we'll explore the common patterns for agentic systems we've seen in production. We'...

10. [Self-correcting Code Generation Using Multi-Step Agent](https://deepsense.ai/resource/self-correcting-code-generation-using-multi-step-agent/) - This cookbook demonstrates how to build a self-correcting code generation pipeline using the smolage...

11. [A self-correcting multi-agent LLM framework for language- ...](https://www.nature.com/articles/s44387-025-00057-z) - by D Park · 2026 · Cited by 1 — We present MCP-SIM (Memory-Coordinated Physics-Aware Simulation), a ...

12. [10 Things Developers Want from their Agentic IDEs in 2025](https://redmonk.com/kholterhoff/2025/12/22/10-things-developers-want-from-their-agentic-ides-in-2025/) - AWS introduced Kiro this summer, an agentic IDE which differentiates itself through its dual spec-dr...

