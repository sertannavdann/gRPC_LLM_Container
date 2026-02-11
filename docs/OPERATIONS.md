# Operations Guide

**Last Updated**: February 2026

## Table of Contents
1. [Monitoring](#monitoring)
2. [Troubleshooting](#troubleshooting)
3. [Performance Tuning](#performance-tuning)
4. [Backup & Recovery](#backup--recovery)
5. [Common Tasks](#common-tasks)

---

## Monitoring

### Service Health Checks

```bash
# Orchestrator
curl http://localhost:8003/admin/health

# Dashboard
curl http://localhost:8001/health

# UI
curl http://localhost:5001

# Prometheus
curl http://localhost:9090/-/healthy

# Grafana
curl http://localhost:3000/api/health
```

### Grafana Dashboards

**Access**: http://localhost:3000 (admin/admin)

**NEXUS Modules Dashboard**:
- Module status (enabled/disabled/failed)
- Build & validation rates
- Container CPU/memory (cAdvisor)
- LIDM delegation counts
- Provider latency

**Prometheus Targets**: http://localhost:9090/targets

### Prometheus Metrics

**Custom Metrics**:
```
nexus_module_builds_total          # Module build attempts
nexus_module_validations_total     # Validation runs
nexus_module_installs_total        # Successful installs
nexus_module_status{category, platform}  # 0=disabled, 1=enabled, 2=failed
nexus_credential_operations_total  # Credential store/retrieve
```

**Query Examples**:
```promql
# Modules in failed state
nexus_module_status{status="failed"}

# Module validation failure rate
rate(nexus_module_validations_total{result="failure"}[5m])

# Container CPU usage
container_cpu_usage_seconds_total{name=~"orchestrator|dashboard"}
```

### Alert Rules

**Location**: `config/prometheus/rules/pipeline_alerts.yml`

**Alerts**:
- `ModuleValidationFailures` - >5 failures in 5min
- `ModulesInFailedState` - Any modules in failed state
- `ContainerHighCPU` - >80% CPU for 5min
- `ContainerHighMemory` - >80% memory for 5min

**Notification**: Currently logs only (Slack/PagerDuty planned)

### Log Management

**Locations**:
- `logs/error.log` - Errors and warnings
- `logs/debug.log` - Debug and info logs

**Makefile Commands**:
```bash
make logs-errors     # View error log
make logs-debug      # View debug log
make logs-core       # Orchestrator + dashboard logs
make logs-adapters   # Adapter-specific logs
```

**Tail Live Logs**:
```bash
docker-compose logs -f orchestrator
docker-compose logs -f dashboard
docker-compose logs -f --tail=100 orchestrator
```

**Search Logs**:
```bash
grep "ERROR" logs/error.log | tail -20
grep "Module" logs/debug.log | grep "enabled"
```

---

## Troubleshooting

### Services Not Starting

**Symptoms**: `docker-compose up` fails

**Solutions**:
1. Check Docker daemon: `docker ps`
2. Check port conflicts: `lsof -i :8001` (or 8003, 5001, etc.)
3. Check disk space: `df -h`
4. Clear old containers: `docker-compose down && docker-compose up`
5. Rebuild images: `make docker-build`

### Module Not Loading

**Symptoms**: Module not in `/admin/modules`

**Solutions**:
1. Check manifest syntax: `cat modules/{cat}/{plat}/manifest.json | jq .`
2. Check Python syntax: `python -m py_compile modules/{cat}/{plat}/adapter.py`
3. Check logs: `make logs-core | grep "Module"`
4. Restart orchestrator: `docker-compose restart orchestrator`

### Adapter Failing

**Symptoms**: Module enabled but no data in `/context`

**Solutions**:
1. Check credentials: `curl http://localhost:8003/admin/credentials/{platform}`
2. Test adapter directly (add debug endpoint temporarily)
3. Check for exceptions: `make logs-errors | grep "{platform}"`
4. Reload module: `POST /admin/modules/{cat}/{plat}/reload`

### High CPU Usage

**Symptoms**: Container using >80% CPU

**Solutions**:
1. Check Grafana dashboard for culprit service
2. Identify workload: LLM inference? Context aggregation?
3. Scale horizontally (add orchestrator replicas)
4. Reduce LIDM tier thresholds (use standard more often)
5. Optimize adapter queries (add caching)

### High Memory Usage

**Symptoms**: Container using >80% memory

**Solutions**:
1. Check for memory leaks: Monitor over time
2. Restart services: `docker-compose restart {service}`
3. Reduce context window: Edit `routing_config.json`
4. Clear adapter caches: `curl -X POST http://localhost:8001/adapters/clear-cache`

### Pipeline UI Not Updating

**Symptoms**: React Flow nodes frozen

**Solutions**:
1. Check SSE connection: Browser DevTools → Network → `pipeline-state`
2. Verify dashboard health: `curl http://localhost:8001/health`
3. Check CORS: Ensure localhost:5001 allowed
4. Refresh page (SSE auto-reconnect)

---

## Performance Tuning

### LIDM Tier Thresholds

**Location**: `config/routing_config.json`

**Default**:
```json
{
  "lidm_delegation_threshold": 0.7,
  "performance_constraints": {
    "max_latency_ms": 5000,
    "max_cost_per_request": 0.05
  }
}
```

**Tuning**:
- **Lower threshold (0.5)**: More queries go to heavy tier (slower, better quality)
- **Higher threshold (0.9)**: More queries go to standard tier (faster, lower quality)

**Command**:
```bash
curl -X PUT http://localhost:8003/admin/routing-config \
  -H "Content-Type: application/json" \
  -d '{"lidm_delegation_threshold": 0.8, ...}'
```

### Context Compaction

**Settings**: `shared/context_manager.py`

**Default**: Keep last 6 message pairs

**Tuning**:
- **Increase (10)**: More context, slower inference, higher token usage
- **Decrease (4)**: Less context, faster inference, lower token usage

### Adapter Caching

**Current**: No caching (fetch every time)

**Planned**: Redis cache with TTL

**Manual Workaround** (in adapter):
```python
class MyAdapter(BaseAdapter[T]):
    _cache = {}
    _cache_ttl = 300  # 5 minutes

    async def fetch_raw(self):
        now = time.time()
        if "data" in self._cache and now - self._cache["timestamp"] < self._cache_ttl:
            return self._cache["data"]

        data = await self._fetch_from_api()
        self._cache = {"data": data, "timestamp": now}
        return data
```

### Database Optimization

**Finance Query Performance**:
- Add indexes: `CREATE INDEX idx_timestamp ON transactions(timestamp)`
- Pagination: Use `LIMIT` and `OFFSET`
- Date range queries: Filter on indexed timestamp column

---

## Backup & Recovery

### Module Registry

**Location**: `data/module_registry.db`

**Backup**:
```bash
docker cp orchestrator:/app/data/module_registry.db ./backups/module_registry_$(date +%Y%m%d).db
```

**Restore**:
```bash
docker cp ./backups/module_registry_20260211.db orchestrator:/app/data/module_registry.db
docker-compose restart orchestrator
```

### Credential Store

**Location**: `data/module_credentials.db`

**Backup** (encrypted at rest, safe to copy):
```bash
docker cp orchestrator:/app/data/module_credentials.db ./backups/credentials_$(date +%Y%m%d).db
```

**Restore**:
```bash
docker cp ./backups/credentials_20260211.db orchestrator:/app/data/module_credentials.db
docker-compose restart orchestrator
```

**Important**: Backup `MODULE_ENCRYPTION_KEY` separately (1Password, AWS Secrets Manager).

### Configuration

**Files**:
- `config/routing_config.json`
- `.env`
- `docker-compose.yaml`

**Backup**:
```bash
tar -czf config_backup_$(date +%Y%m%d).tar.gz config/ .env docker-compose.yaml
```

**Restore**:
```bash
tar -xzf config_backup_20260211.tar.gz
make docker-restart
```

### LLM Models

**Location**: `llm_service/models/`

**Backup** (large files, use selective backup):
```bash
# Only backup model manifests (small)
cp llm_service/models/*.json backups/models/

# For full model backup (multi-GB):
rsync -av llm_service/models/ /backup/llm_models/
```

---

## Common Tasks

### Add New Module

```bash
# 1. Create directory
mkdir -p modules/my_category/my_platform

# 2. Create manifest, adapter, tests
# (see EXTENSION-GUIDE.md)

# 3. Restart orchestrator to discover
docker-compose restart orchestrator

# 4. Enable module
curl -X POST http://localhost:8003/admin/modules/my_category/my_platform/enable

# 5. Verify
curl http://localhost:8003/admin/modules | jq '.modules[] | select(.platform=="my_platform")'
```

### Rotate Credentials

```bash
# 1. Update credentials
curl -X POST http://localhost:8003/admin/credentials \
  -H "Content-Type: application/json" \
  -d '{"platform": "openweather", "credentials": {"api_key": "new-key"}}'

# 2. Reload module
curl -X POST http://localhost:8003/admin/modules/weather/openweather/reload

# 3. Verify
curl http://localhost:8003/admin/credentials/openweather/check
```

### Update Routing Config

```bash
# 1. Edit config
vim config/routing_config.json

# 2. Hot-reload via API
curl -X PUT http://localhost:8003/admin/routing-config \
  -H "Content-Type: application/json" \
  -d @config/routing_config.json

# 3. Verify
curl http://localhost:8003/admin/routing-config | jq .
```

### Clear Logs

```bash
# Truncate logs
> logs/error.log
> logs/debug.log

# Or rotate manually
mv logs/error.log logs/error.log.1
mv logs/debug.log logs/debug.log.1
docker-compose restart orchestrator dashboard
```

### Rebuild All Services

```bash
make docker-down
make docker-build
make docker-up
make test-health
```

---

## See Also

- [ARCHITECTURE.md](./ARCHITECTURE.md) - System architecture
- [SECURITY.md](./SECURITY.md) - Security practices
- [KNOWN-ISSUES.md](./KNOWN-ISSUES.md) - Current issues
