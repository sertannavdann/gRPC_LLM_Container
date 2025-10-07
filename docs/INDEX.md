# Documentation Index

## Getting Started

**New to the project?** Start here:
1. Read [00_OVERVIEW.md](./00_OVERVIEW.md) - Understand the system philosophy and architecture
2. Review [01_ARCHITECTURE.md](./01_ARCHITECTURE.md) - Learn about component interactions
3. Follow the [Quick Start](../README.MD#quick-start) in the main README

**Want to build features?** Focus on:
- [02_AGENT_SERVICE.md](./02_AGENT_SERVICE.md) - Core orchestration logic
- [05_TESTING.md](./05_TESTING.md) - Testing patterns

**Interested in integrations?** Check out:
- [03_APPLE_INTEGRATION.md](./03_APPLE_INTEGRATION.md) - Native macOS/iOS integration
- [04_N8N_INTEGRATION.md](./04_N8N_INTEGRATION.md) - Workflow automation

## Documentation Structure

### [00_OVERVIEW.md](./00_OVERVIEW.md)
**Purpose**: High-level introduction to the system

**Topics Covered**:
- Agent-as-denominator philosophy
- Service responsibilities and tech stacks
- Data flow examples
- Architectural decisions (gRPC, LangGraph, SQLite, C++ bridge)
- Scalability considerations
- Integration patterns

**Audience**: Everyone - start here

**Reading Time**: 15 minutes

---

### [01_ARCHITECTURE.md](./01_ARCHITECTURE.md)
**Purpose**: Deep dive into system architecture

**Topics Covered**:
- Component diagrams with mermaid
- Agent service architecture (ToolRegistry, LLMOrchestrator, ToolExecutor, WorkflowBuilder)
- LLM service stack (llama.cpp, Metal acceleration, streaming, JSON grammar)
- Chroma service (vector storage, embedding strategy)
- Tool service (registry pattern, web search, rate limiting)
- gRPC communication protocols
- Docker Compose deployment
- Performance characteristics and throughput
- Security considerations

**Audience**: Developers, architects

**Reading Time**: 30 minutes

**Prerequisites**: Read 00_OVERVIEW.md first

---

### [02_AGENT_SERVICE.md](./02_AGENT_SERVICE.md)
**Purpose**: Implementation details of the agent orchestration layer

**Topics Covered**:
- Core components breakdown (ToolRegistry, LLMOrchestrator, ToolExecutor, WorkflowBuilder)
- Circuit breaker implementation
- LangGraph workflow construction
- State management (AgentState TypedDict, state flow)
- SQLite checkpointing and persistence
- Tool registration patterns
- Context window management
- Error handling strategies
- Performance optimizations
- Monitoring and observability

**Audience**: Agent service developers

**Reading Time**: 40 minutes

**Prerequisites**: 
- Read 00_OVERVIEW.md and 01_ARCHITECTURE.md
- Familiarity with LangGraph concepts

**Key Code Sections**:
- Tool registration example: Lines 150-220
- Workflow builder: Lines 300-380
- State flow example: Lines 450-490

---

### [03_APPLE_INTEGRATION.md](./03_APPLE_INTEGRATION.md)
**Purpose**: Comprehensive guide to native Apple platform integration

**Topics Covered**:
- **Why Apple Integration**: Native API access requirements, PyObjC limitations
- **Architecture**: C++ gRPC service → Objective-C++ bridge → Swift App Intents flow
- **Component Deep Dive**:
  - C++ gRPC service implementation
  - Objective-C++ MetalBridge (EventKit, Contacts frameworks)
  - Swift App Intents for Siri/Shortcuts
- **Deployment Models**: Development (non-containerized), Server, Desktop App
- **Security & Permissions**: EventKit entitlements, TCC database, sandboxing
- **Extending the Bridge**: Step-by-step guide to add new native features (example: Contacts query)
- **Testing**: XCTest for Objective-C++, integration tests
- **Troubleshooting**: Permission issues, build failures, Xcode debugging
- **Future Enhancements**: Full Swift app, iOS support, on-device inference

**Audience**: 
- Developers working on Apple integrations
- Anyone curious about the C++/Objective-C++/Swift bridge rationale

**Reading Time**: 45 minutes

**Prerequisites**: 
- Basic understanding of C++ and Objective-C
- Familiarity with Apple frameworks (EventKit, Contacts)
- Read 01_ARCHITECTURE.md for context

**Key Sections**:
- Why C++ over alternatives: Lines 15-30
- Objective-C++ bridge example: Lines 120-200
- Swift App Intent example: Lines 220-290
- Adding new features: Lines 380-520

---

### [04_N8N_INTEGRATION.md](./04_N8N_INTEGRATION.md)
**Purpose**: Guide to integrating the agent system with n8n workflow automation

**Topics Covered**:
- **What is n8n**: Overview, benefits, comparison to Zapier
- **Integration Methods**:
  - REST API wrapper (Flask, recommended for MVP)
  - Custom gRPC node (future)
- **Use Case Recipes** (5 detailed examples):
  1. Scheduled meeting digest
  2. Smart email auto-responder
  3. Document sync & summarization
  4. Multi-step research pipeline
  5. Conditional branching (invoice approval)
- **Advanced Patterns**:
  - Loop until condition met
  - Parallel agent queries
  - Human-in-the-loop approvals
- **Error Handling**: Retry with exponential backoff, fallback actions
- **Monitoring**: Key metrics, webhook integration
- **Security**: API authentication, rate limiting, input validation
- **Deployment**: Docker network setup, persistent workflows, backup strategies
- **Complete Example**: End-to-end customer support automation workflow

**Audience**: 
- Workflow automation engineers
- Integration specialists
- Product managers exploring automation capabilities

**Reading Time**: 50 minutes

**Prerequisites**: 
- Basic understanding of workflow automation
- Read 00_OVERVIEW.md for system context

**Key Sections**:
- REST API wrapper implementation: Lines 30-90
- Recipe examples: Lines 100-400
- Advanced patterns: Lines 420-550
- Complete E2E workflow: Lines 650-730

---

### [05_TESTING.md](./05_TESTING.md)
**Purpose**: Comprehensive testing strategy and implementation guide

**Topics Covered**:
- **Testing Philosophy**: Pyramid model, deterministic tests, fast feedback
- **Test Levels**:
  - Unit tests (70%): Individual function testing, validation, circuit breaker
  - Integration tests (25%): Service interactions, LLM client, agent-tool integration
  - E2E tests (5%): Full workflow, multi-turn conversations
- **Mock Harness**: Local testing without Docker, stateful mocks
- **Modular Service Tests**: Independent service validation
- **Test Automation**: 
  - CI/CD pipeline (GitHub Actions example)
  - Local test script (run_tests.sh)
- **Debugging**: Logging, output capture, isolating failures, mock inspection
- **Performance Testing**: Load testing with Locust
- **Coverage Goals**: Targets and reporting
- **Best Practices**: 10 key principles
- **Troubleshooting**: Common issues and solutions

**Audience**: 
- All developers
- QA engineers
- DevOps engineers

**Reading Time**: 35 minutes

**Prerequisites**: 
- Familiarity with pytest
- Read 02_AGENT_SERVICE.md for context on what's being tested

**Key Sections**:
- Mock harness architecture: Lines 180-250
- CI/CD pipeline YAML: Lines 420-490
- Test automation script: Lines 500-570

---

## Quick Reference

### Common Tasks

| Task | Documentation | Key Sections |
|------|--------------|--------------|
| Understand system design | 00_OVERVIEW.md, 01_ARCHITECTURE.md | Service responsibilities, Data flow |
| Add a new tool | 02_AGENT_SERVICE.md | Tool registration (lines 150-220) |
| Integrate with Apple APIs | 03_APPLE_INTEGRATION.md | Extending the bridge (lines 380-520) |
| Create n8n workflow | 04_N8N_INTEGRATION.md | Use case recipes (lines 100-400) |
| Write tests | 05_TESTING.md | Test levels, Mock harness |
| Deploy to production | 01_ARCHITECTURE.md | Deployment architecture, Security |
| Troubleshoot issues | 03_APPLE_INTEGRATION.md, 05_TESTING.md | Troubleshooting sections |

### Glossary

- **Agent**: The central orchestrator service that coordinates all other services
- **Tool**: A function the agent can call (e.g., schedule_meeting, search_web)
- **Circuit Breaker**: Pattern that disables failing tools after N failures
- **LangGraph**: Framework for building stateful agent workflows
- **Checkpoint**: Saved agent state for conversation resumption
- **Thread ID**: Identifier for a conversation session
- **Context Window**: Recent conversation history sent to LLM
- **Protobuf**: Binary serialization format for gRPC messages
- **MetalBridge**: Objective-C++ component bridging C++ to Apple frameworks
- **App Intents**: Apple framework for Siri/Shortcuts integration
- **n8n**: Self-hosted workflow automation platform

### External Resources

- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [gRPC Python Guide](https://grpc.io/docs/languages/python/)
- [llama.cpp GitHub](https://github.com/ggerganov/llama.cpp)
- [ChromaDB Documentation](https://docs.trychroma.com/)
- [n8n Documentation](https://docs.n8n.io/)
- [Apple EventKit Guide](https://developer.apple.com/documentation/eventkit)
- [App Intents Documentation](https://developer.apple.com/documentation/appintents)

## Documentation Maintenance

### When to Update

- **Add new service**: Update 00_OVERVIEW.md and 01_ARCHITECTURE.md
- **Add new tool**: Update 02_AGENT_SERVICE.md (tool registration section)
- **Change Apple integration**: Update 03_APPLE_INTEGRATION.md
- **New n8n pattern**: Add recipe to 04_N8N_INTEGRATION.md
- **New test type**: Update 05_TESTING.md

### Style Guide

- Use **mermaid diagrams** for architecture visuals
- Include **code examples** with full context (not snippets)
- Add **"Why This Matters"** sections to explain design decisions
- Use **real-world examples** in recipes
- Keep **prerequisites** and **reading time** updated
- Add **line number references** for long code sections

### Contributing

To improve documentation:
1. Fork the repository
2. Make changes in `docs/` directory
3. Test all code examples
4. Update this INDEX.md if adding new files
5. Submit pull request with description

## Feedback

Found an issue or have a suggestion?
- Open an issue on GitHub
- Tag with `documentation` label
- Provide specific section references

---

**Last Updated**: January 2025  
**Documentation Version**: 1.0  
**System Version**: Sprint 2 MVP
