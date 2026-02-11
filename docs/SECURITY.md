# Security Architecture

**Last Updated**: February 2026

## Table of Contents
1. [Credential Management](#credential-management)
2. [Sandbox Isolation](#sandbox-isolation)
3. [Audit Logging](#audit-logging)
4. [Threat Model](#threat-model)
5. [Security Best Practices](#security-best-practices)
6. [Incident Response](#incident-response)

---

## Credential Management

### Encryption at Rest

**Method**: Fernet (symmetric encryption from cryptography.io library)

**Key Management**:
- `MODULE_ENCRYPTION_KEY` environment variable (32-byte base64-encoded)
- Generated once, stored securely
- Never logged or exposed in responses

**Storage**:
- Location: `data/module_credentials.db` (SQLite)
- Schema:
  ```sql
  CREATE TABLE credentials (
      platform TEXT PRIMARY KEY,
      encrypted_data BLOB NOT NULL,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
  );
  ```

**Encryption Flow**:
```python
from cryptography.fernet import Fernet

# Generate key (once)
key = Fernet.generate_key()  # Store in MODULE_ENCRYPTION_KEY

# Encrypt credentials
f = Fernet(key)
encrypted = f.encrypt(json.dumps(credentials).encode())

# Decrypt credentials
decrypted = f.decrypt(encrypted)
credentials = json.loads(decrypted.decode())
```

### Credential Injection

**Runtime Injection**: Credentials are injected into adapter instances at runtime, never passed to LLM context.

**Adapter Access**:
```python
class MyAdapter(BaseAdapter[T]):
    async def fetch_raw(self):
        api_key = self._get_credential("api_key")  # Decrypted on demand
        # Use api_key...
```

**LLM Protection**:
- Credentials NOT in conversation history
- Credentials NOT in tool call arguments
- Credentials NOT in log files (except debug mode, truncated)

### Credential Rotation

**Current**: Manual rotation via Admin API

**Process**:
1. Update credentials via POST `/admin/credentials`
2. Reload module via POST `/admin/modules/{cat}/{plat}/reload`
3. Verify with GET `/admin/credentials/{platform}/check`

**Planned** (Q3 2026): Automatic expiration warnings and rotation

---

## Sandbox Isolation

### Purpose

Isolate untrusted code execution (user-submitted Python, module validation).

### Implementation

**Service**: `sandbox_service` (gRPC on port 50057)

**Container**: Separate Docker container with restricted capabilities

**Restrictions**:
- No network access (except whitelisted domains)
- Limited filesystem access (read-only except `/tmp`)
- CPU limit: 1 core
- Memory limit: 512MB
- Execution timeout: 30 seconds

**Modes**:
1. **Restricted**: Default, no network, minimal file access
2. **Testing**: Network allowed for API testing
3. **Integration**: Full access for integration tests

### Code Execution

**Request**:
```python
sandbox_client.ExecuteCode(
    code="print('hello')",
    language="python",
    timeout_seconds=30,
    env_vars={}  # No sensitive data
)
```

**Response**:
```python
{
    "stdout": "hello\n",
    "stderr": "",
    "exit_code": 0,
    "timeout": False,
    "execution_time_ms": 15
}
```

### Security Boundaries

**Prevented**:
- File system traversal (`../../../etc/passwd`)
- Network exfiltration (blocked egress)
- Resource exhaustion (CPU/memory limits)
- Privilege escalation (non-root user)

**Allowed**:
- Standard library imports
- pytest execution
- Temporary file creation in `/tmp`

---

## Audit Logging

### Current Implementation

**Logs**: `logs/error.log`, `logs/debug.log`

**Rotating File Handler**:
- Max size: 10MB per file
- Backup count: 3 files
- Rotation: Automatic on size limit

**Log Levels**:
- `ERROR` → `error.log` (critical issues only)
- `WARNING` → `error.log` (potential issues)
- `INFO` → `debug.log` (normal operations)
- `DEBUG` → `debug.log` (detailed debugging)

### Logged Events

**Credential Operations**:
- `store_credential(platform)` → INFO
- `get_credential(platform)` → DEBUG (no actual credential logged)
- `credential_validation_failed(platform)` → WARNING

**Module Operations**:
- `module_loaded(category, platform)` → INFO
- `module_enabled(category, platform)` → INFO
- `module_failed(category, platform, error)` → ERROR

**Admin API**:
- `config_updated(user, changes)` → WARNING
- `module_uninstalled(category, platform, user)` → WARNING

**Authentication** (planned):
- `login_success(user, ip)` → INFO
- `login_failed(user, ip, reason)` → WARNING
- `unauthorized_access(user, endpoint)` → WARNING

### Future: Centralized Logging (ELK Stack)

**Planned Q4 2026**:
- Elasticsearch for log storage
- Logstash for log aggregation
- Kibana for visualization
- Structured JSON logging

---

## Threat Model

### Threat Actors

1. **Malicious User**: Tries to steal credentials or abuse system
2. **Compromised Module**: Malicious code in community module
3. **External Attacker**: Network-based attack on exposed services
4. **Insider Threat**: Developer with access to encryption keys

### Attack Surfaces

#### 1. Admin API (Port 8003)

**Threats**:
- Unauthorized module installation
- Credential theft
- Configuration tampering

**Mitigations**:
- ✅ CORS enabled (development mode)
- ❌ No authentication (planned Q3 2026)
- ✅ Credentials never returned in responses
- ✅ Audit logging

**Risk**: HIGH (no auth in development)

#### 2. Dashboard API (Port 8001)

**Threats**:
- Context data leakage
- Adapter data manipulation
- Denial of service

**Mitigations**:
- ✅ Read-only endpoints
- ❌ No rate limiting (planned Q3 2026)
- ✅ No credential exposure
- ✅ Health checks

**Risk**: MEDIUM

#### 3. gRPC Services

**Threats**:
- Direct service access bypassing orchestrator
- Malicious tool calls
- Context injection attacks

**Mitigations**:
- ✅ Internal network only (Docker bridge)
- ✅ No external exposure
- ✅ Input validation on all RPCs
- ❌ No authentication (planned Q3 2026)

**Risk**: LOW (internal only)

#### 4. Module System

**Threats**:
- Malicious module code execution
- Credential exfiltration
- Backdoor installation

**Mitigations**:
- 🚧 Sandbox validation (Track A4, in progress)
- ❌ No approval gates (planned Track C3)
- ✅ Encrypted credential storage
- ✅ Module registry tracking

**Risk**: HIGH (no validation yet)

#### 5. UI Service

**Threats**:
- XSS attacks
- CSRF attacks
- Session hijacking

**Mitigations**:
- ✅ React XSS protection (JSX escaping)
- ❌ No CSRF tokens (planned Q3 2026)
- ❌ No session management (planned Q3 2026)

**Risk**: MEDIUM

---

## Security Best Practices

### For Module Developers

1. **Never Hardcode Credentials**
   ```python
   # ❌ BAD
   api_key = "hardcoded-key-12345"

   # ✅ GOOD
   api_key = self._get_credential("api_key")
   ```

2. **Validate External Data**
   ```python
   # ✅ GOOD
   async def fetch_raw(self):
       response = await httpx.get(url)
       response.raise_for_status()  # Validate status
       data = response.json()
       assert "required_field" in data  # Validate schema
       return data
   ```

3. **Use HTTPS Only**
   ```python
   # ✅ GOOD
   url = "https://api.example.com"  # Always HTTPS
   ```

4. **Sanitize User Input**
   ```python
   # ✅ GOOD
   user_input = user_input.strip()
   if not re.match(r'^[a-zA-Z0-9_-]+$', user_input):
       raise ValueError("Invalid input")
   ```

### For System Administrators

1. **Rotate Encryption Keys**
   - Change `MODULE_ENCRYPTION_KEY` quarterly
   - Re-encrypt all credentials after key rotation

2. **Monitor Logs**
   - Watch for `unauthorized_access` warnings
   - Alert on `module_failed` errors
   - Review `credential_validation_failed` logs

3. **Update Dependencies**
   - Keep Python packages up-to-date
   - Run `pip-audit` monthly
   - Review Dependabot PRs

4. **Network Segmentation**
   - Keep gRPC services on internal network
   - Firewall rules: Only expose 8001, 8003, 5001
   - Use reverse proxy (nginx) for HTTPS

---

## Incident Response

### Security Incident Workflow

1. **Detection**
   - Monitor logs for suspicious activity
   - Prometheus alerts for anomalies
   - User reports

2. **Containment**
   - Disable affected module: `POST /admin/modules/{cat}/{plat}/disable`
   - Revoke compromised credentials: `DELETE /admin/credentials/{platform}`
   - Stop services: `docker-compose down`

3. **Investigation**
   - Review logs: `make logs-errors`
   - Check module code: `cat modules/{cat}/{plat}/adapter.py`
   - Analyze network traffic (if applicable)

4. **Recovery**
   - Remove malicious module: `DELETE /admin/modules/{cat}/{plat}`
   - Rotate affected credentials
   - Restart services: `make docker-up`

5. **Post-Mortem**
   - Document incident
   - Update threat model
   - Implement preventive measures

### Emergency Contacts

**Internal Team**:
- Lead Developer: [contact info]
- Security Lead: [contact info]

**External**:
- Hosting Provider: [support info]
- Incident Response Firm: [contact info]

---

## Compliance

### GDPR Considerations (Future)

**Planned Q3 2026**:
- User data export endpoint
- Right to be forgotten (delete all user data)
- Privacy policy and terms of service
- Cookie consent management

### SOC 2 Considerations (Future)

**Planned Q4 2026**:
- Access control policies
- Encryption in transit (TLS)
- Backup and disaster recovery
- Vendor risk management

---

## Security Roadmap

### Q2 2026
- [ ] OAuth2 authentication for Admin API
- [ ] Sandbox validation for modules (Track A4)
- [ ] Rate limiting on all endpoints
- [ ] CSRF protection for UI

### Q3 2026
- [ ] Approval gates for module installation
- [ ] Automatic credential expiration warnings
- [ ] Security scanning for community modules
- [ ] Penetration testing

### Q4 2026
- [ ] Bug bounty program
- [ ] Security audit by third party
- [ ] SOC 2 Type 1 compliance
- [ ] Incident response runbook

---

## Reporting Security Issues

**Email**: security@nexus.example.com (placeholder)

**PGP Key**: [public key]

**Process**:
1. Email with detailed description
2. We acknowledge within 24 hours
3. We provide fix timeline within 72 hours
4. We coordinate disclosure after fix

**Responsible Disclosure**: Please allow 90 days before public disclosure.

---

## See Also

- [ARCHITECTURE.md](./ARCHITECTURE.md) - System architecture
- [EXTENSION-GUIDE.md](./EXTENSION-GUIDE.md) - Module development
- [OPERATIONS.md](./OPERATIONS.md) - Monitoring and troubleshooting
