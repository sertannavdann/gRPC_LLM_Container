# Documentation Index

Welcome to the gRPC LLM Agent Framework (NEXUS) documentation.

## Getting Started
- [Quick Start Guide](../README.MD) - Installation and first run
- [Architecture Overview](./ARCHITECTURE.md) - Current system state
- [Operations Guide](./OPERATIONS.md) - Running and monitoring

## Development
- [Extension Guide](./EXTENSION-GUIDE.md) - Build modules and adapters
- [API Reference](./API-REFERENCE.md) - REST and gRPC APIs
- [Glossary](./GLOSSARY.md) - Terms and concepts

## Planning
- [Roadmap](./ROADMAP.md) - What's done and what's next
- [Known Issues](./KNOWN-ISSUES.md) - Current limitations

## Security
- [Security Architecture](./SECURITY.md) - Credentials, sandbox, audit

## Archive
- [Project Vision](./archive/PROJECT_VISION.md) - Aspirational design
- [Archive Index](./archive/_INDEX.md) - Historical documentation

---

## Quick Links

### Service Ports
- **Dashboard Service**: http://localhost:8001
- **UI Service**: http://localhost:5001
- **Admin API**: http://localhost:8003
- **Grafana**: http://localhost:3000
- **Prometheus**: http://localhost:9090
- **cAdvisor**: http://localhost:8080

### Key Commands
```bash
make docker-up          # Start all services
make docker-down        # Stop all services
make showroom           # Run integration tests
make logs-errors        # View error logs
make logs-debug         # View debug logs
```

### Testing
- Unit tests: `make test-unit`
- Integration tests: `make test-integration`
- E2E tests: `make test-e2e`
- Showroom demo: `make showroom`
