"""
Security Utilities & Validation Layer for SUMO AI MCP
Provides strict input validation, command injection prevention,
password hashing, JWT verification, and OAuth 2.1 PKCE security primitives.
"""

import os
import re
import hmac
import time
import base64
import hashlib
import secrets
import logging
from typing import Optional, Dict, Any, Tuple

# Configure security audit logger
logger = logging.getLogger("sumo_mcp.security")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(asctime)s] [SECURITY] [%(levelname)s] %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# Security constants
DEFAULT_JWT_SECRET = os.environ.get("JWT_SECRET") or os.environ.get("SUMO_AUTH_SECRET") or secrets.token_hex(32)
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_SECONDS = 7 * 24 * 3600  # 7 days
MAX_TRIPS_LIMIT = 5000
MIN_TRIPS_LIMIT = 1
MAX_DURATION_SECONDS = 86400  # 24 hours
MIN_DURATION_SECONDS = 10
MAX_BBOX_SPAN = 0.05  # ~5km maximum bounding box span to prevent Overpass API exhaustion

# In-memory auth stores (for OAuth 2.1 code exchange and active sessions)
AUTH_CODES: Dict[str, Dict[str, Any]] = {}
ACTIVE_SESSIONS: Dict[str, Dict[str, Any]] = {}
USERS_DB: Dict[str, Dict[str, Any]] = {}

# Pre-populate demo user for instant plug-and-play testing
def _init_default_users():
    if "admin@sumo.ai" not in USERS_DB:
        salt = secrets.token_hex(16)
        password_hash = hash_password("admin123", salt)
        USERS_DB["admin@sumo.ai"] = {
            "id": "usr_admin_001",
            "email": "admin@sumo.ai",
            "name": "SUMO Admin",
            "role": "admin",
            "salt": salt,
            "password_hash": password_hash,
            "created_at": time.time(),
        }
    if "developer@sumo.ai" not in USERS_DB:
        salt = secrets.token_hex(16)
        password_hash = hash_password("sumo2026", salt)
        USERS_DB["developer@sumo.ai"] = {
            "id": "usr_dev_002",
            "email": "developer@sumo.ai",
            "name": "AI Engineer",
            "role": "developer",
            "salt": salt,
            "password_hash": password_hash,
            "created_at": time.time(),
        }

# =============================================================================
# 1. INPUT SANITIZATION & COMMAND INJECTION PREVENTION
# =============================================================================

def sanitize_location_query(query: str) -> str:
    """
    Sanitizes place names or location search queries.
    Strips shell metacharacters, control characters, and limits string length.
    """
    if not query:
        return "Coimbatore"
    # Disallow shell metacharacters: ; & | ` $ > < ! { } [ ] \n \r
    sanitized = re.sub(r"[;&|`$><!{}[\]\n\r\t\"'\\]", "", str(query).strip())
    # Truncate overly long queries
    if len(sanitized) > 100:
        sanitized = sanitized[:100]
    return sanitized or "Coimbatore"


def validate_and_clamp_bbox(bbox_str: str) -> str:
    """
    Validates bounding box coordinate string and strictly clamps dimensions
    to prevent Overpass API Denial-of-Service and excessive memory usage.
    Expected format: 'min_lon,min_lat,max_lon,max_lat'
    """
    parts = str(bbox_str).strip().split(",")
    if len(parts) != 4:
        raise ValueError(f"Invalid bounding box format: expected 4 comma-separated values, got {len(parts)}")

    try:
        min_lon = float(parts[0].strip())
        min_lat = float(parts[1].strip())
        max_lon = float(parts[2].strip())
        max_lat = float(parts[3].strip())
    except ValueError:
        raise ValueError("Invalid bounding box values: coordinates must be floating point numbers")

    # Enforce geographic validity
    if not (-180.0 <= min_lon <= 180.0 and -180.0 <= max_lon <= 180.0):
        raise ValueError("Longitude out of bounds (-180 to 180)")
    if not (-90.0 <= min_lat <= 90.0 and -90.0 <= max_lat <= 90.0):
        raise ValueError("Latitude out of bounds (-90 to 90)")

    # Ensure min < max
    if min_lon > max_lon:
        min_lon, max_lon = max_lon, min_lon
    if min_lat > max_lat:
        min_lat, max_lat = max_lat, min_lat

    # Clamp span to MAX_BBOX_SPAN (~2.5km - 5km radius) to protect public APIs
    center_lon = (min_lon + max_lon) / 2.0
    center_lat = (min_lat + max_lat) / 2.0
    half_span = min(MAX_BBOX_SPAN, max(0.01, (max_lon - min_lon))) / 2.0
    half_span_lat = min(MAX_BBOX_SPAN, max(0.01, (max_lat - min_lat))) / 2.0

    c_min_lon = round(center_lon - half_span, 4)
    c_min_lat = round(center_lat - half_span_lat, 4)
    c_max_lon = round(center_lon + half_span, 4)
    c_max_lat = round(center_lat + half_span_lat, 4)

    return f"{c_min_lon:.4f},{c_min_lat:.4f},{c_max_lon:.4f},{c_max_lat:.4f}"


def clamp_simulation_parameters(trips: int, duration: int, density: Optional[str] = None) -> Tuple[int, int, str]:
    """
    Clamps simulation parameters to safe operational bounds.
    """
    # Density validation
    valid_densities = {"low": 250, "medium": 600, "high": 1200, "congested": 2000}
    clean_density = "medium"
    if density:
        d_lower = str(density).strip().lower()
        if d_lower in valid_densities:
            clean_density = d_lower
            trips = valid_densities[d_lower]

    # Clamp trips
    safe_trips = max(MIN_TRIPS_LIMIT, min(MAX_TRIPS_LIMIT, int(trips)))
    # Clamp duration
    safe_duration = max(MIN_DURATION_SECONDS, min(MAX_DURATION_SECONDS, int(duration)))

    return safe_trips, safe_duration, clean_density


def prevent_path_traversal(target_file: str, allowed_base_dir: str = ".") -> str:
    """
    Prevents path traversal attacks by resolving target path and verifying it stays within allowed directory.
    """
    base_abs = os.path.abspath(allowed_base_dir)
    target_abs = os.path.abspath(os.path.join(base_abs, target_file))
    if not target_abs.startswith(base_abs):
        raise PermissionError(f"Security Alert: Path traversal attempt blocked for '{target_file}'")
    return target_abs


# =============================================================================
# 2. CRYPTOGRAPHIC PASSWORD HASHING (PBKDF2-HMAC-SHA256)
# =============================================================================

def hash_password(password: str, salt: str) -> str:
    """
    Hashes a password using PBKDF2-HMAC-SHA256 with 100,000 iterations and salt.
    """
    key = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    )
    return base64.b64encode(key).decode('ascii')


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    """
    Secure constant-time verification of passwords.
    """
    calculated_hash = hash_password(password, salt)
    return hmac.compare_digest(calculated_hash, expected_hash)


# =============================================================================
# 3. JSON WEB TOKEN (JWT) IMPLEMENTATION (HS256)
# =============================================================================

def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def _base64url_decode(data_str: str) -> bytes:
    padding = '=' * (4 - (len(data_str) % 4)) if len(data_str) % 4 != 0 else ''
    return base64.urlsafe_b64decode((data_str + padding).encode('ascii'))


def create_jwt_token(payload: Dict[str, Any], secret: str = DEFAULT_JWT_SECRET, expires_in: int = JWT_EXPIRATION_SECONDS) -> str:
    """
    Creates a secure, signed JWT token with standard claims.
    """
    now = int(time.time())
    full_payload = {
        "iss": "sumo-ai-mcp",
        "iat": now,
        "exp": now + expires_in,
        **payload
    }
    header = {"alg": "HS256", "typ": "JWT"}
    header_json = json_dumps(header)
    payload_json = json_dumps(full_payload)

    header_b64 = _base64url_encode(header_json.encode('utf-8'))
    payload_b64 = _base64url_encode(payload_json.encode('utf-8'))
    message = f"{header_b64}.{payload_b64}".encode('ascii')

    signature = hmac.new(secret.encode('utf-8'), message, hashlib.sha256).digest()
    sig_b64 = _base64url_encode(signature)

    return f"{header_b64}.{payload_b64}.{sig_b64}"


def verify_jwt_token(token: str, secret: str = DEFAULT_JWT_SECRET) -> Optional[Dict[str, Any]]:
    """
    Verifies signature and expiration of a JWT token. Returns payload if valid, None if invalid.
    """
    if not token or not isinstance(token, str):
        return None

    # Handle Bearer prefix if passed
    if token.startswith("Bearer "):
        token = token[7:].strip()

    parts = token.split(".")
    if len(parts) != 3:
        return None

    header_b64, payload_b64, sig_b64 = parts
    try:
        message = f"{header_b64}.{payload_b64}".encode('ascii')
        expected_sig = hmac.new(secret.encode('utf-8'), message, hashlib.sha256).digest()
        actual_sig = _base64url_decode(sig_b64)

        if not hmac.compare_digest(expected_sig, actual_sig):
            logger.warning("JWT signature verification failed")
            return None

        payload_bytes = _base64url_decode(payload_b64)
        payload = json_loads(payload_bytes.decode('utf-8'))

        # Check expiration
        now = int(time.time())
        if "exp" in payload and payload["exp"] < now:
            logger.warning(f"JWT expired (exp: {payload['exp']}, now: {now})")
            return None

        return payload
    except Exception as e:
        logger.warning(f"Failed to decode or verify JWT: {e}")
        return None


# Helper json serializers without requiring extra imports
import json

def json_dumps(obj: Any) -> str:
    return json.dumps(obj, separators=(',', ':'), sort_keys=True)

def json_loads(s: str) -> Any:
    return json.loads(s)


# =============================================================================
# 4. USER REGISTRATION & AUTHENTICATION MANAGEMENT
# =============================================================================

def register_user(email: str, password: str, name: str = "", role: str = "user") -> Dict[str, Any]:
    """
    Registers a new user with secure password hashing.
    """
    email_clean = str(email).strip().lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email_clean):
        raise ValueError("Invalid email address format")

    if not password or len(password) < 6:
        raise ValueError("Password must be at least 6 characters long")

    _init_default_users()

    if email_clean in USERS_DB:
        raise ValueError(f"User with email '{email_clean}' already exists")

    salt = secrets.token_hex(16)
    password_hash = hash_password(password, salt)
    user_id = f"usr_{secrets.token_hex(8)}"

    user_record = {
        "id": user_id,
        "email": email_clean,
        "name": name.strip() or email_clean.split("@")[0],
        "role": role if role in ["admin", "developer", "user"] else "user",
        "salt": salt,
        "password_hash": password_hash,
        "created_at": time.time(),
    }
    USERS_DB[email_clean] = user_record
    logger.info(f"User successfully registered: {email_clean} ({user_id})")

    token = create_jwt_token({
        "sub": user_id,
        "email": email_clean,
        "role": user_record["role"],
        "name": user_record["name"]
    })

    return {
        "id": user_id,
        "email": email_clean,
        "name": user_record["name"],
        "role": user_record["role"],
        "token": token
    }


def authenticate_user(email: str, password: str) -> Dict[str, Any]:
    """
    Authenticates user and returns JWT token and profile info.
    """
    email_clean = str(email).strip().lower()
    _init_default_users()

    user = USERS_DB.get(email_clean)
    if not user:
        logger.warning(f"Failed login attempt for non-existent user: {email_clean}")
        raise ValueError("Invalid email or password")

    if not verify_password(password, user["salt"], user["password_hash"]):
        logger.warning(f"Failed login attempt (wrong password) for: {email_clean}")
        raise ValueError("Invalid email or password")

    token = create_jwt_token({
        "sub": user["id"],
        "email": user["email"],
        "role": user["role"],
        "name": user["name"]
    })

    logger.info(f"User authenticated successfully: {email_clean}")
    return {
        "id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "role": user["role"],
        "token": token
    }


# =============================================================================
# 5. OAUTH 2.1 AUTHORIZATION CODE FLOW WITH PKCE & REDIRECTS
# =============================================================================

def generate_authorization_code(client_id: str, redirect_uri: str, user_id: str, code_challenge: Optional[str] = None, scope: str = "sumo:simulation") -> str:
    """
    Generates a secure, short-lived authorization code for OAuth 2.1 redirection.
    """
    code = secrets.token_urlsafe(32)
    AUTH_CODES[code] = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "user_id": user_id,
        "code_challenge": code_challenge,
        "scope": scope,
        "expires_at": time.time() + 300  # 5 minutes validity
    }
    return code


def exchange_authorization_code(code: str, client_id: str, redirect_uri: str, code_verifier: Optional[str] = None) -> Dict[str, Any]:
    """
    Exchanges authorization code for JWT access token with PKCE verification.
    """
    record = AUTH_CODES.pop(code, None)
    if not record:
        raise ValueError("Invalid or expired authorization code")

    if record["expires_at"] < time.time():
        raise ValueError("Authorization code has expired")

    if record["client_id"] != client_id:
        raise ValueError("Client ID mismatch")

    if record["redirect_uri"] != redirect_uri:
        raise ValueError("Redirect URI mismatch")

    # PKCE Verification if code_challenge was provided
    if record.get("code_challenge"):
        if not code_verifier:
            raise ValueError("code_verifier required for PKCE validation")
        # S256 challenge check
        challenge = _base64url_encode(hashlib.sha256(code_verifier.encode('ascii')).digest())
        if not hmac.compare_digest(challenge, record["code_challenge"]):
            raise ValueError("Invalid PKCE code_verifier")

    user_id = record["user_id"]
    # Find user
    user = next((u for u in USERS_DB.values() if u["id"] == user_id), None)
    email = user["email"] if user else "user@sumo.ai"
    role = user["role"] if user else "user"

    access_token = create_jwt_token({
        "sub": user_id,
        "email": email,
        "role": role,
        "scope": record["scope"]
    })

    return {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": JWT_EXPIRATION_SECONDS,
        "scope": record["scope"]
    }

# Initialize default users
_init_default_users()
