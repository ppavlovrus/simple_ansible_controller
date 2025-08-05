# Security Guide

## Overview

The LLM-Powered Ansible Controller handles sensitive operations and data, making security a critical concern. This guide covers security considerations, best practices, and implementation details.

## Security Architecture

### Defense in Depth

The system implements multiple layers of security:

1. **Input Validation** - Validate all inputs at multiple levels
2. **Access Control** - Implement proper authentication and authorization
3. **Data Protection** - Encrypt sensitive data in transit and at rest
4. **Audit Logging** - Comprehensive logging for security monitoring
5. **Safety Validation** - Prevent dangerous operations

## Input Validation

### API Input Validation

All API inputs are validated using Pydantic models:

```python
class PlaybookGenerationRequest(BaseModel):
    description: str = Field(..., min_length=1, max_length=1000)
    hosts: str = Field(..., regex=r'^[a-zA-Z0-9_-]+$')
    inventory: str = Field(..., regex=r'^[a-zA-Z0-9/_.-]+$')
    safety_level: str = Field("medium", regex=r'^(low|medium|high)$')
```

### LLM Input Sanitization

```python
def sanitize_description(description: str) -> str:
    """Sanitize natural language description."""
    # Remove potentially dangerous characters
    sanitized = re.sub(r'[<>"\']', '', description)
    # Limit length
    return sanitized[:1000]

def validate_hosts(hosts: str) -> bool:
    """Validate host specification."""
    # Only allow safe host patterns
    return bool(re.match(r'^[a-zA-Z0-9_-]+$', hosts))
```

### Template Variable Validation

```python
def validate_template_variables(variables: Dict[str, Any], schema: Dict) -> List[str]:
    """Validate template variables against JSON schema."""
    errors = []
    
    # Check required fields
    for field in schema.get("required", []):
        if field not in variables:
            errors.append(f"Required field missing: {field}")
    
    # Check field types and constraints
    for field_name, field_value in variables.items():
        if field_name in schema.get("properties", {}):
            field_schema = schema["properties"][field_name]
            
            # Type validation
            expected_type = field_schema.get("type")
            if expected_type == "string" and not isinstance(field_value, str):
                errors.append(f"Field {field_name} must be a string")
            
            # Enum validation
            if "enum" in field_schema and field_value not in field_schema["enum"]:
                errors.append(f"Field {field_name} must be one of: {field_schema['enum']}")
    
    return errors
```

## Access Control

### API Authentication

**Current Implementation**: No authentication (development mode)

**Production Recommendations**:

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt

security = HTTPBearer()

async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify JWT token."""
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

@app.post("/generate-playbook/")
async def generate_playbook(
    request: PlaybookGenerationRequest,
    user: dict = Depends(verify_token)
):
    # Check user permissions
    if not user.get("can_generate_playbooks"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
```

### Role-Based Access Control

```python
from enum import Enum
from typing import List

class Role(Enum):
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"

class Permission(Enum):
    GENERATE_PLAYBOOKS = "generate_playbooks"
    EXECUTE_TASKS = "execute_tasks"
    MANAGE_TEMPLATES = "manage_templates"
    VIEW_LOGS = "view_logs"

ROLE_PERMISSIONS = {
    Role.ADMIN: [p.value for p in Permission],
    Role.OPERATOR: [
        Permission.GENERATE_PLAYBOOKS.value,
        Permission.EXECUTE_TASKS.value,
        Permission.VIEW_LOGS.value
    ],
    Role.VIEWER: [Permission.VIEW_LOGS.value]
}

def check_permission(user_role: Role, permission: Permission) -> bool:
    """Check if user has required permission."""
    return permission.value in ROLE_PERMISSIONS.get(user_role, [])
```

## Data Protection

### API Key Security

**Environment Variables**:
```bash
# Store API keys securely
export OPENAI_API_KEY="sk-your-key-here"
export ANTHROPIC_API_KEY="sk-ant-your-key-here"

# Use secrets management
echo "your-api-key" | docker secret create openai_api_key -
```

**Configuration Validation**:
```python
def validate_api_keys():
    """Validate API key configuration."""
    errors = []
    
    if Config.LLM_PROVIDER == "openai" and not Config.OPENAI_API_KEY:
        errors.append("OPENAI_API_KEY is required")
    
    if Config.LLM_PROVIDER == "anthropic" and not Config.ANTHROPIC_API_KEY:
        errors.append("ANTHROPIC_API_KEY is required")
    
    # Validate API key format
    if Config.OPENAI_API_KEY and not Config.OPENAI_API_KEY.startswith("sk-"):
        errors.append("Invalid OpenAI API key format")
    
    if Config.ANTHROPIC_API_KEY and not Config.ANTHROPIC_API_KEY.startswith("sk-ant-"):
        errors.append("Invalid Anthropic API key format")
    
    return errors
```

### Database Security

**Connection Security**:
```python
# Use SSL connections
DATABASE_URL = "postgresql://user:pass@host:5432/db?sslmode=require"

# Connection pooling with security
engine = create_engine(
    DATABASE_URL,
    pool_size=20,
    max_overflow=30,
    pool_pre_ping=True,
    pool_recycle=3600
)
```

**Data Encryption**:
```python
from cryptography.fernet import Fernet

class EncryptedField:
    """Encrypt sensitive database fields."""
    
    def __init__(self, key: bytes):
        self.cipher = Fernet(key)
    
    def encrypt(self, data: str) -> str:
        """Encrypt data."""
        return self.cipher.encrypt(data.encode()).decode()
    
    def decrypt(self, encrypted_data: str) -> str:
        """Decrypt data."""
        return self.cipher.decrypt(encrypted_data.encode()).decode()
```

### SSH Key Management

**Secure Key Storage**:
```python
import os
from pathlib import Path

class SSHKeyManager:
    """Manage SSH keys securely."""
    
    def __init__(self, key_dir: str = "/app/keys"):
        self.key_dir = Path(key_dir)
        self.key_dir.mkdir(mode=0o700, exist_ok=True)
    
    def store_key(self, key_name: str, private_key: str, public_key: str):
        """Store SSH key pair securely."""
        private_path = self.key_dir / f"{key_name}_id_rsa"
        public_path = self.key_dir / f"{key_name}_id_rsa.pub"
        
        # Write private key with restricted permissions
        private_path.write_text(private_key)
        private_path.chmod(0o600)
        
        # Write public key
        public_path.write_text(public_key)
        public_path.chmod(0o644)
    
    def get_key_path(self, key_name: str) -> str:
        """Get private key path."""
        return str(self.key_dir / f"{key_name}_id_rsa")
```

## Safety Validation

### Dangerous Pattern Detection

```python
DANGEROUS_PATTERNS = [
    # File system operations
    "rm -rf",
    "rm -rf /",
    "dd if=",
    "dd of=",
    
    # Disk operations
    "mkfs",
    "fdisk",
    "parted",
    "format",
    
    # System operations
    "shutdown",
    "reboot",
    "halt",
    "poweroff",
    "init 0",
    "init 6",
    
    # Network operations
    "iptables -F",
    "iptables -X",
    "ufw --force reset",
    
    # User operations
    "userdel",
    "groupdel",
    "passwd -d",
]

def detect_dangerous_patterns(content: str) -> List[str]:
    """Detect dangerous patterns in playbook content."""
    detected = []
    content_lower = content.lower()
    
    for pattern in DANGEROUS_PATTERNS:
        if pattern in content_lower:
            detected.append(pattern)
    
    return detected
```

### Safety Level Enforcement

```python
class SafetyLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

SAFETY_RULES = {
    SafetyLevel.LOW: {
        "max_score": 50,
        "blocked_modules": [],
        "require_approval": False
    },
    SafetyLevel.MEDIUM: {
        "max_score": 70,
        "blocked_modules": [],
        "require_approval": False
    },
    SafetyLevel.HIGH: {
        "max_score": 90,
        "blocked_modules": ["shell", "command", "raw", "script"],
        "require_approval": True
    }
}

def validate_safety_level(content: str, safety_level: SafetyLevel) -> Dict[str, Any]:
    """Validate content against safety level rules."""
    rules = SAFETY_RULES[safety_level]
    violations = []
    
    # Check for blocked modules
    for module in rules["blocked_modules"]:
        if f"{module}:" in content:
            violations.append(f"Blocked module: {module}")
    
    # Check for dangerous patterns
    dangerous_patterns = detect_dangerous_patterns(content)
    if dangerous_patterns:
        violations.extend([f"Dangerous pattern: {pattern}" for pattern in dangerous_patterns])
    
    # Calculate safety score
    base_score = 100
    score_deduction = len(violations) * 20
    safety_score = max(0, base_score - score_deduction)
    
    return {
        "is_valid": safety_score >= rules["max_score"] and len(violations) == 0,
        "safety_score": safety_score,
        "violations": violations,
        "require_approval": rules["require_approval"]
    }
```

## Audit Logging

### Comprehensive Logging

```python
import logging
import json
from datetime import datetime
from typing import Dict, Any

class SecurityLogger:
    """Security-focused logging."""
    
    def __init__(self):
        self.logger = logging.getLogger("security")
        self.logger.setLevel(logging.INFO)
    
    def log_playbook_generation(self, user: str, request: Dict[str, Any], result: Dict[str, Any]):
        """Log playbook generation attempt."""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "event": "playbook_generation",
            "user": user,
            "request": {
                "description": request.get("description"),
                "hosts": request.get("hosts"),
                "safety_level": request.get("safety_level")
            },
            "result": {
                "success": result.get("is_valid", False),
                "safety_score": result.get("safety_score", 0),
                "errors": result.get("validation_errors", [])
            }
        }
        
        self.logger.info(json.dumps(log_entry))
    
    def log_task_execution(self, user: str, task_id: str, playbook_path: str):
        """Log task execution."""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "event": "task_execution",
            "user": user,
            "task_id": task_id,
            "playbook_path": playbook_path
        }
        
        self.logger.info(json.dumps(log_entry))
    
    def log_security_violation(self, user: str, violation_type: str, details: Dict[str, Any]):
        """Log security violations."""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "event": "security_violation",
            "user": user,
            "violation_type": violation_type,
            "details": details,
            "severity": "high"
        }
        
        self.logger.warning(json.dumps(log_entry))
```

### Log Analysis

```python
import re
from collections import Counter

class SecurityAnalyzer:
    """Analyze security logs for threats."""
    
    def __init__(self, log_file: str):
        self.log_file = log_file
    
    def analyze_violations(self, hours: int = 24) -> Dict[str, Any]:
        """Analyze security violations in the last N hours."""
        violations = []
        
        with open(self.log_file, 'r') as f:
            for line in f:
                if '"event": "security_violation"' in line:
                    try:
                        log_entry = json.loads(line)
                        violations.append(log_entry)
                    except json.JSONDecodeError:
                        continue
        
        # Count violation types
        violation_types = Counter([v["violation_type"] for v in violations])
        
        # Find suspicious users
        user_violations = Counter([v["user"] for v in violations])
        suspicious_users = [user for user, count in user_violations.items() if count > 5]
        
        return {
            "total_violations": len(violations),
            "violation_types": dict(violation_types),
            "suspicious_users": suspicious_users,
            "time_period_hours": hours
        }
```

## Network Security

### API Security Headers

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

app = FastAPI()

# Security headers
@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "default-src 'self'"
    return response

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://yourdomain.com"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

# Trusted hosts
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["yourdomain.com", "api.yourdomain.com"]
)
```

### Rate Limiting

```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.post("/generate-playbook/")
@limiter.limit("10/minute")
async def generate_playbook(request: Request):
    # Implementation
    pass

@app.post("/templates/")
@limiter.limit("5/minute")
async def create_template(request: Request):
    # Implementation
    pass
```

## Incident Response

### Security Incident Handling

```python
class SecurityIncidentHandler:
    """Handle security incidents."""
    
    def __init__(self):
        self.logger = SecurityLogger()
    
    def handle_dangerous_playbook(self, user: str, content: str, safety_score: float):
        """Handle dangerous playbook generation attempt."""
        # Log the incident
        self.logger.log_security_violation(
            user=user,
            violation_type="dangerous_playbook",
            details={
                "safety_score": safety_score,
                "content_preview": content[:200]
            }
        )
        
        # Block the request
        raise HTTPException(
            status_code=400,
            detail="Dangerous playbook detected and blocked"
        )
    
    def handle_rate_limit_exceeded(self, user: str, endpoint: str):
        """Handle rate limit exceeded."""
        self.logger.log_security_violation(
            user=user,
            violation_type="rate_limit_exceeded",
            details={"endpoint": endpoint}
        )
        
        # Implement progressive delays
        time.sleep(60)  # 1 minute delay
    
    def handle_unauthorized_access(self, user: str, resource: str):
        """Handle unauthorized access attempt."""
        self.logger.log_security_violation(
            user=user,
            violation_type="unauthorized_access",
            details={"resource": resource}
        )
        
        # Block user temporarily
        # Implementation depends on your user management system
```

## Security Monitoring

### Real-time Monitoring

```python
import asyncio
from typing import List, Dict

class SecurityMonitor:
    """Real-time security monitoring."""
    
    def __init__(self):
        self.violation_threshold = 10
        self.time_window_minutes = 60
        self.recent_violations: List[Dict] = []
    
    async def monitor_violations(self):
        """Monitor for security violations."""
        while True:
            # Check recent violations
            current_time = datetime.now()
            recent_violations = [
                v for v in self.recent_violations
                if (current_time - v["timestamp"]).total_seconds() < self.time_window_minutes * 60
            ]
            
            if len(recent_violations) > self.violation_threshold:
                await self.trigger_alert(recent_violations)
            
            # Clean up old violations
            self.recent_violations = recent_violations
            
            await asyncio.sleep(60)  # Check every minute
    
    async def trigger_alert(self, violations: List[Dict]):
        """Trigger security alert."""
        # Send email alert
        # Send Slack notification
        # Create incident ticket
        pass
    
    def add_violation(self, violation: Dict):
        """Add new violation to monitoring."""
        self.recent_violations.append(violation)
```

## Compliance

### GDPR Compliance

```python
class GDPRCompliance:
    """GDPR compliance features."""
    
    def __init__(self):
        self.data_retention_days = 30
    
    def anonymize_user_data(self, user_id: str):
        """Anonymize user data for GDPR compliance."""
        # Implementation for data anonymization
        pass
    
    def export_user_data(self, user_id: str) -> Dict[str, Any]:
        """Export user data for GDPR right to access."""
        # Implementation for data export
        pass
    
    def delete_user_data(self, user_id: str):
        """Delete user data for GDPR right to be forgotten."""
        # Implementation for data deletion
        pass
```

### SOC 2 Compliance

```python
class SOC2Compliance:
    """SOC 2 compliance features."""
    
    def __init__(self):
        self.audit_logs = []
    
    def log_access_control(self, user: str, resource: str, action: str):
        """Log access control events for SOC 2."""
        audit_entry = {
            "timestamp": datetime.now().isoformat(),
            "user": user,
            "resource": resource,
            "action": action,
            "result": "success"
        }
        self.audit_logs.append(audit_entry)
    
    def generate_compliance_report(self) -> Dict[str, Any]:
        """Generate SOC 2 compliance report."""
        # Implementation for compliance reporting
        pass
```

## Security Checklist

### Pre-Production Checklist

- [ ] Enable authentication and authorization
- [ ] Configure SSL/TLS for all connections
- [ ] Set up proper API key management
- [ ] Implement rate limiting
- [ ] Configure security headers
- [ ] Set up audit logging
- [ ] Test safety validation
- [ ] Review and update firewall rules
- [ ] Set up monitoring and alerting
- [ ] Document security procedures

### Ongoing Security Tasks

- [ ] Regular security audits
- [ ] Update dependencies
- [ ] Monitor security logs
- [ ] Review access controls
- [ ] Test incident response procedures
- [ ] Update security documentation
- [ ] Conduct security training
- [ ] Review compliance requirements

## Security Resources

### Tools and Libraries

- **OWASP ZAP**: Web application security testing
- **Bandit**: Python security linter
- **Safety**: Check Python dependencies for known vulnerabilities
- **TruffleHog**: Detect secrets in code
- **SonarQube**: Code quality and security analysis

### Security Standards

- **OWASP Top 10**: Web application security risks
- **NIST Cybersecurity Framework**: Security best practices
- **ISO 27001**: Information security management
- **SOC 2**: Security, availability, and confidentiality controls

### Security Contacts

- **Security Team**: security@yourcompany.com
- **Incident Response**: incident@yourcompany.com
- **Compliance Team**: compliance@yourcompany.com 