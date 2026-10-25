# 🛡️ Security Architecture & Constraints Specification

## 1. Threat Model & Security Posture
The **SUMO AI MCP Server** integrates Large Language Models (LLMs) and external AI agents directly with local and remote system environments, executing simulation pipelines consisting of OpenStreetMap downloaders, `netconvert`, and `sumo` simulation binaries.

To prevent Remote Code Execution (RCE), Denial of Service (DoS), unauthorized simulation triggers, and path traversal, the following security constraints are enforced at every layer of the architecture:

---

## 2. Security Constraints Matrix

| Layer | Constraint | Threat Mitigated | Implementation |
| :--- | :--- | :--- | :--- |
| **Input Validation** | Strict regex & whitelist sanitization | Command Injection / Shell Splitting | `security_utils.sanitize_location_query()` |
| **Geographic Clamping** | Maximum Bounding Box span (`0.05` deg / ~2.5km - 5km) | Overpass API bans, memory exhaustion, crash | `security_utils.validate_and_clamp_bbox()` |
| **Parameter Bounding** | Trips bounded (1–5,000), Duration bounded (10s–86,400s) | Resource exhaustion & host CPU starvation | `security_utils.clamp_simulation_parameters()` |
| **Path Traversal Protection** | Explicit root directory resolution | Arbitrary File Read / Write | `security_utils.prevent_path_traversal()` |
| **Command Execution** | Disallow `shell=True`; use explicit argument arrays | Arbitrary shell execution | `subprocess.run([binary, ...], shell=False)` |
| **Authentication** | OAuth 2.1 Authorization Code Flow with PKCE & HS256 JWT | Unauthorized tool execution / impersonation | `security_utils.create_jwt_token()` |
| **Password Security** | PBKDF2-HMAC-SHA256 (100,000 rounds) + Cryptographic Salt | Credential theft & Rainbow table attacks | `security_utils.hash_password()` |
| **Transport Security** | Dual Transport isolation (STDIO for local IDEs, SSE/HTTP with Bearer token) | Man-In-The-Middle & Unauthenticated Web requests | FastMCP / FastAPI security headers |
| **Audit Logging** | Structured logging of authentication and simulation invocations | Non-repudiation & forensic observability | `sumo_mcp.security` logger |

---

## 3. OAuth 2.1 & Redirect Signup Security Protocol

When an AI model or client connects to SUMO AI MCP:
1. **Redirect Protocol**:
   - The AI client initiates connection via `/auth/authorize` with `client_id`, `redirect_uri`, `state`, and optional PKCE `code_challenge`.
   - If the user is unauthenticated, they are redirected to `/auth/portal` with AI model context.
   - Upon completing signup or login, an authorization code is generated with a short 5-minute TTL.
   - The user is redirected back to the AI client with `redirect_uri?code=...&state=...`.
2. **State & CSRF Protection**:
   - The `state` parameter is validated to prevent Cross-Site Request Forgery (CSRF).
   - PKCE (Proof Key for Code Exchange) using `S256` protects authorization codes from interception.
3. **Session & Token Verification**:
   - Access tokens use HMAC-SHA256 (HS256) with standard claims (`iss`, `sub`, `exp`, `iat`, `role`).
   - Expired tokens and mismatched signatures are rejected with HTTP 401 Unauthorized.

---

## 4. Subprocess Execution Guardrails

All calls to `netconvert`, `sumo`, `sumo-gui`, `osmGet.py`, and `randomTrips.py` must strictly adhere to:
- **No shell expansion**: Never use `shell=True` or format strings in shell commands.
- **Safe Executable Lookup**: Binaries and scripts are verified against configured `SUMO_HOME` and system PATH.
- **Explicit Timeout & Return Code Checks**: Subprocesses are executed with `check=True` and inspected `CalledProcessError`.
