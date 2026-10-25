"""
OAuth 2.0 / 2.1 Authentication & Redirect Signup Gateway for SUMO AI MCP
Provides secure user signup, login, OAuth2 authorization code flow with PKCE,
token exchange, and multi-AI model redirect handling.
"""

import os
import sys
import json
import urllib.parse
from typing import Optional, Dict, Any

from fastapi import FastAPI, Request, Form, HTTPException, Depends, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr

import security_utils

app = FastAPI(
    title="SUMO AI MCP – Authentication & AI Redirect Gateway",
    description="OAuth 2.1 authorization server, user signup portal, and multi-AI model integration bridge",
    version="1.0.0"
)

# Enable CORS for AI clients and web frontends
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Supported AI Model Registry
SUPPORTED_AI_MODELS = [
    {
        "id": "claude",
        "name": "Anthropic Claude 3.5 Sonnet / Desktop",
        "provider": "Anthropic",
        "icon": "🟣",
        "description": "Native MCP stdio and SSE support for Claude Desktop and Claude Code",
        "transport": "stdio/sse"
    },
    {
        "id": "chatgpt",
        "name": "OpenAI ChatGPT / Custom GPTs",
        "provider": "OpenAI",
        "icon": "🟢",
        "description": "OpenAPI 3.1 actions integration with OAuth 2.0 redirect authentication",
        "transport": "sse/http"
    },
    {
        "id": "gemini",
        "name": "Google Gemini 1.5 / 2.0 & Antigravity",
        "provider": "Google",
        "icon": "🔵",
        "description": "Multi-modal reasoning and Antigravity IDE MCP extension",
        "transport": "stdio/sse"
    },
    {
        "id": "cursor",
        "name": "Cursor AI IDE",
        "provider": "Cursor",
        "icon": "⚡",
        "description": "In-editor MCP server protocol for autonomous traffic engineering agent",
        "transport": "stdio"
    },
    {
        "id": "ollama",
        "name": "Ollama / Local LLM (Llama 3, DeepSeek)",
        "provider": "Local / Open Source",
        "icon": "🦙",
        "description": "Completely offline and private local simulation tool orchestration",
        "transport": "sse/http"
    }
]

# Request Schemas
class SignupRequest(BaseModel):
    email: str
    password: str
    name: Optional[str] = ""
    role: Optional[str] = "developer"
    redirect_uri: Optional[str] = None
    state: Optional[str] = None
    client_id: Optional[str] = None

class LoginRequest(BaseModel):
    email: str
    password: str
    redirect_uri: Optional[str] = None
    state: Optional[str] = None
    client_id: Optional[str] = None

class TokenExchangeRequest(BaseModel):
    grant_type: str
    code: str
    client_id: str
    redirect_uri: str
    code_verifier: Optional[str] = None


# =============================================================================
# API ENDPOINTS
# =============================================================================

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "sumo-ai-mcp-auth-gateway",
        "version": "1.0.0",
        "supported_models_count": len(SUPPORTED_AI_MODELS)
    }


@app.get("/auth/models")
async def list_models():
    """Lists all supported AI models and their connection specifications."""
    return {
        "count": len(SUPPORTED_AI_MODELS),
        "models": SUPPORTED_AI_MODELS
    }


@app.get("/auth/authorize")
async def oauth_authorize(
    response_type: str = "code",
    client_id: str = "ai_client",
    redirect_uri: Optional[str] = None,
    state: Optional[str] = None,
    scope: str = "sumo:simulation",
    code_challenge: Optional[str] = None,
    code_challenge_method: Optional[str] = None,
    ai_model: Optional[str] = None
):
    """
    OAuth 2.1 Authorization Endpoint:
    When an AI model requests access, redirects the user to the signup/login portal
    with the selected AI model's context preserved.
    """
    if response_type != "code":
        raise HTTPException(status_code=400, detail="Unsupported response_type: only 'code' is supported")

    # Build redirect URL to the modern interactive signup/login portal
    query_params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri or "https://chatgpt.com/aip/callback",
        "state": state or "",
        "scope": scope,
        "ai_model": ai_model or "generic"
    }
    if code_challenge:
        query_params["code_challenge"] = code_challenge

    portal_url = f"/auth/portal?{urllib.parse.urlencode(query_params)}"
    return RedirectResponse(url=portal_url, status_code=status.HTTP_302_FOUND)


@app.post("/auth/signup")
async def signup_user(req: SignupRequest):
    """Registers a new user and generates OAuth redirect if requested."""
    try:
        user = security_utils.register_user(
            email=req.email,
            password=req.password,
            name=req.name or "",
            role=req.role or "developer"
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # If redirect_uri is provided, generate OAuth authorization code
    redirect_url = None
    code = None
    if req.redirect_uri:
        code = security_utils.generate_authorization_code(
            client_id=req.client_id or "ai_client",
            redirect_uri=req.redirect_uri,
            user_id=user["id"]
        )
        sep = "&" if "?" in req.redirect_uri else "?"
        state_param = f"&state={urllib.parse.quote(req.state)}" if req.state else ""
        redirect_url = f"{req.redirect_uri}{sep}code={code}{state_param}"

    return {
        "status": "success",
        "message": "User registered successfully",
        "user": {
            "id": user["id"],
            "email": user["email"],
            "name": user["name"],
            "role": user["role"]
        },
        "token": user["token"],
        "authorization_code": code,
        "redirect_url": redirect_url
    }


@app.post("/auth/login")
async def login_user(req: LoginRequest):
    """Authenticates user and generates OAuth redirect if requested."""
    try:
        user = security_utils.authenticate_user(
            email=req.email,
            password=req.password
        )
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    redirect_url = None
    code = None
    if req.redirect_uri:
        code = security_utils.generate_authorization_code(
            client_id=req.client_id or "ai_client",
            redirect_uri=req.redirect_uri,
            user_id=user["id"]
        )
        sep = "&" if "?" in req.redirect_uri else "?"
        state_param = f"&state={urllib.parse.quote(req.state)}" if req.state else ""
        redirect_url = f"{req.redirect_uri}{sep}code={code}{state_param}"

    return {
        "status": "success",
        "message": "User authenticated successfully",
        "user": {
            "id": user["id"],
            "email": user["email"],
            "name": user["name"],
            "role": user["role"]
        },
        "token": user["token"],
        "authorization_code": code,
        "redirect_url": redirect_url
    }


@app.post("/auth/token")
async def exchange_token(
    grant_type: str = Form(...),
    code: str = Form(...),
    client_id: str = Form(...),
    redirect_uri: str = Form(...),
    code_verifier: Optional[str] = Form(None)
):
    """OAuth 2.1 Token Exchange endpoint (RFC 6749 / RFC 7636)."""
    if grant_type != "authorization_code":
        raise HTTPException(status_code=400, detail="Only grant_type='authorization_code' is supported")

    try:
        token_data = security_utils.exchange_authorization_code(
            code=code,
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_verifier=code_verifier
        )
        return token_data
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/auth/me")
async def get_current_user(request: Request):
    """Returns profile for currently authenticated user via Bearer JWT."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = auth_header[7:].strip()
    payload = security_utils.verify_jwt_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token is invalid or expired")

    return {
        "authenticated": True,
        "user_id": payload.get("sub"),
        "email": payload.get("email"),
        "role": payload.get("role", "developer"),
        "scope": payload.get("scope", "sumo:simulation")
    }


# =============================================================================
# INTERACTIVE SIGNUP / LOGIN / AI REDIRECT PORTAL (HTML)
# =============================================================================

@app.get("/", response_class=HTMLResponse)
@app.get("/auth/portal", response_class=HTMLResponse)
async def auth_portal_html(
    client_id: Optional[str] = "ai_client",
    redirect_uri: Optional[str] = None,
    state: Optional[str] = "",
    scope: Optional[str] = "sumo:simulation",
    ai_model: Optional[str] = "claude"
):
    """
    Renders a stunning modern dark-mode interactive authentication & AI redirect portal.
    Allows user to select their AI model, sign up or log in, and seamlessly redirects
    back to the connected AI application!
    """
    models_json = json.dumps(SUPPORTED_AI_MODELS)
    safe_redirect = redirect_uri or "/auth/success"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SUMO AI MCP – AI Model Integration & Authentication Gateway</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-dark: #0a0e17;
            --bg-card: rgba(18, 24, 38, 0.75);
            --bg-card-hover: rgba(26, 35, 54, 0.85);
            --border-glow: rgba(56, 189, 248, 0.25);
            --border-active: #38bdf8;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --accent-cyan: #38bdf8;
            --accent-green: #34d399;
            --accent-purple: #a855f7;
            --accent-orange: #fb923c;
            --gradient-title: linear-gradient(135deg, #38bdf8 0%, #818cf8 50%, #c084fc 100%);
            --gradient-btn: linear-gradient(135deg, #0284c7 0%, #6366f1 100%);
        }}

        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: 'Outfit', sans-serif;
        }}

        body {{
            background-color: var(--bg-dark);
            color: var(--text-main);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            justifyContent: center;
            padding: 24px 16px;
            background-image: 
                radial-gradient(circle at 15% 20%, rgba(56, 189, 248, 0.12) 0%, transparent 40%),
                radial-gradient(circle at 85% 80%, rgba(168, 85, 247, 0.12) 0%, transparent 40%),
                radial-gradient(circle at 50% 50%, rgba(52, 211, 153, 0.05) 0%, transparent 50%);
            background-attachment: fixed;
        }}

        .portal-container {{
            width: 100%;
            max-width: 940px;
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 28px;
            background: var(--bg-card);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border: 1px solid var(--border-glow);
            border-radius: 24px;
            padding: 36px;
            box-shadow: 0 25px 60px -15px rgba(0, 0, 0, 0.6), 0 0 40px rgba(56, 189, 248, 0.1);
        }}

        @media (max-width: 820px) {{
            .portal-container {{
                grid-template-columns: 1fr;
                padding: 24px;
            }}
        }}

        /* Left Column: AI Model Integration Info */
        .info-col {{
            display: flex;
            flex-direction: column;
            justifyContent: space-between;
        }}

        .badge {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 6px 14px;
            background: rgba(56, 189, 248, 0.12);
            border: 1px solid rgba(56, 189, 248, 0.3);
            border-radius: 9999px;
            color: var(--accent-cyan);
            font-size: 0.82rem;
            font-weight: 600;
            letter-spacing: 0.5px;
            width: fit-content;
            margin-bottom: 14px;
        }}

        .brand-title {{
            font-size: 2.1rem;
            font-weight: 800;
            line-height: 1.2;
            background: var(--gradient-title);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 12px;
        }}

        .brand-subtitle {{
            color: var(--text-muted);
            font-size: 0.95rem;
            line-height: 1.5;
            margin-bottom: 24px;
        }}

        .model-selector-box {{
            background: rgba(10, 14, 23, 0.6);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 16px;
            padding: 16px;
            margin-bottom: 20px;
        }}

        .section-label {{
            font-size: 0.78rem;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: var(--text-muted);
            font-weight: 700;
            margin-bottom: 12px;
            display: block;
        }}

        .models-grid {{
            display: flex;
            flex-direction: column;
            gap: 10px;
        }}

        .model-card {{
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 10px 14px;
            border-radius: 12px;
            border: 1px solid rgba(255, 255, 255, 0.06);
            background: rgba(255, 255, 255, 0.02);
            cursor: pointer;
            transition: all 0.2s ease;
        }}

        .model-card:hover {{
            background: rgba(56, 189, 248, 0.08);
            border-color: rgba(56, 189, 248, 0.3);
            transform: translateY(-1px);
        }}

        .model-card.selected {{
            background: rgba(56, 189, 248, 0.15);
            border-color: var(--accent-cyan);
            box-shadow: 0 0 15px rgba(56, 189, 248, 0.2);
        }}

        .model-icon {{
            font-size: 1.4rem;
        }}

        .model-name {{
            font-size: 0.92rem;
            font-weight: 600;
            color: var(--text-main);
        }}

        .model-provider {{
            font-size: 0.75rem;
            color: var(--text-muted);
        }}

        .security-badge-box {{
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
            margin-top: 14px;
        }}

        .sec-pill {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.72rem;
            padding: 4px 8px;
            border-radius: 6px;
            background: rgba(52, 211, 153, 0.1);
            color: var(--accent-green);
            border: 1px solid rgba(52, 211, 153, 0.25);
        }}

        /* Right Column: Auth Form */
        .auth-col {{
            background: rgba(10, 14, 23, 0.7);
            border: 1px solid rgba(255, 255, 255, 0.07);
            border-radius: 18px;
            padding: 28px;
            display: flex;
            flex-direction: column;
        }}

        .tabs-header {{
            display: flex;
            gap: 8px;
            margin-bottom: 24px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            padding-bottom: 8px;
        }}

        .tab-btn {{
            background: none;
            border: none;
            color: var(--text-muted);
            font-size: 1rem;
            font-weight: 600;
            padding: 8px 16px;
            cursor: pointer;
            border-radius: 8px;
            transition: all 0.2s;
        }}

        .tab-btn.active {{
            color: var(--accent-cyan);
            background: rgba(56, 189, 248, 0.1);
        }}

        .form-group {{
            margin-bottom: 18px;
        }}

        .form-label {{
            display: block;
            font-size: 0.84rem;
            font-weight: 500;
            color: var(--text-muted);
            margin-bottom: 6px;
        }}

        .form-input {{
            width: 100%;
            background: rgba(18, 24, 38, 0.8);
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 10px;
            padding: 12px 14px;
            color: var(--text-main);
            font-size: 0.92rem;
            transition: all 0.2s;
        }}

        .form-input:focus {{
            outline: none;
            border-color: var(--accent-cyan);
            box-shadow: 0 0 10px rgba(56, 189, 248, 0.25);
        }}

        .submit-btn {{
            width: 100%;
            background: var(--gradient-btn);
            color: #fff;
            border: none;
            border-radius: 12px;
            padding: 14px;
            font-size: 1rem;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.25s ease;
            box-shadow: 0 10px 20px -5px rgba(2, 132, 199, 0.4);
            margin-top: 10px;
        }}

        .submit-btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 15px 25px -5px rgba(2, 132, 199, 0.6);
        }}

        .redirect-notice {{
            margin-top: 16px;
            font-size: 0.78rem;
            color: var(--text-muted);
            line-height: 1.4;
            text-align: center;
        }}

        .alert-box {{
            display: none;
            padding: 10px 14px;
            border-radius: 8px;
            font-size: 0.85rem;
            margin-bottom: 16px;
        }}

        .alert-error {{
            background: rgba(239, 68, 68, 0.15);
            border: 1px solid rgba(239, 68, 68, 0.3);
            color: #fca5a5;
        }}

        .alert-success {{
            background: rgba(52, 211, 153, 0.15);
            border: 1px solid rgba(52, 211, 153, 0.3);
            color: #6ee7b7;
        }}

        .quick-credentials {{
            margin-top: 18px;
            padding: 10px;
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.03);
            border: 1px dashed rgba(255, 255, 255, 0.1);
            font-size: 0.78rem;
            color: var(--text-muted);
        }}

        .quick-credentials code {{
            color: var(--accent-cyan);
            font-family: 'JetBrains Mono', monospace;
        }}
    </style>
</head>
<body>

    <div class="portal-container">
        <!-- Left: AI Model Connection Hub -->
        <div class="info-col">
            <div>
                <div class="badge">
                    <span>⚡</span> <span>Model Context Protocol v1.0</span>
                </div>
                <h1 class="brand-title">SUMO AI MCP</h1>
                <p class="brand-subtitle">
                    Intelligent microscopic traffic simulation engine seamlessly connected to any AI model of your choice.
                </p>

                <div class="model-selector-box">
                    <span class="section-label">Select AI Model Integration</span>
                    <div class="models-grid" id="modelsList">
                        <!-- Populated by JavaScript -->
                    </div>
                </div>
            </div>

            <div>
                <div class="security-badge-box">
                    <span class="sec-pill">OAuth 2.1 PKCE</span>
                    <span class="sec-pill">JWT HS256</span>
                    <span class="sec-pill">Command Sanitized</span>
                    <span class="sec-pill">Overpass Clamped</span>
                </div>
            </div>
        </div>

        <!-- Right: Signup / Login & AI Redirect Form -->
        <div class="auth-col">
            <div class="tabs-header">
                <button class="tab-btn active" id="tabSignupBtn" onclick="switchTab('signup')">Sign Up</button>
                <button class="tab-btn" id="tabLoginBtn" onclick="switchTab('login')">Log In</button>
            </div>

            <div id="alertBox" class="alert-box"></div>

            <!-- Signup Form -->
            <form id="signupForm" onsubmit="handleSignup(event)">
                <div class="form-group">
                    <label class="form-label">Full Name</label>
                    <input type="text" id="signupName" class="form-input" placeholder="e.g. Sanjay S" required>
                </div>
                <div class="form-group">
                    <label class="form-label">Email Address</label>
                    <input type="email" id="signupEmail" class="form-input" placeholder="engineer@sumo.ai" required>
                </div>
                <div class="form-group">
                    <label class="form-label">Password</label>
                    <input type="password" id="signupPassword" class="form-input" placeholder="••••••••••••" minlength="6" required>
                </div>
                <button type="submit" class="submit-btn" id="signupSubmitBtn">
                    Sign Up & Authorize AI
                </button>
            </form>

            <!-- Login Form (Hidden by default) -->
            <form id="loginForm" style="display: none;" onsubmit="handleLogin(event)">
                <div class="form-group">
                    <label class="form-label">Email Address</label>
                    <input type="email" id="loginEmail" class="form-input" placeholder="engineer@sumo.ai" required>
                </div>
                <div class="form-group">
                    <label class="form-label">Password</label>
                    <input type="password" id="loginPassword" class="form-input" placeholder="••••••••••••" required>
                </div>
                <button type="submit" class="submit-btn" id="loginSubmitBtn">
                    Log In & Connect AI
                </button>
            </form>

            <div class="quick-credentials">
                <span>Demo Account:</span> <code>admin@sumo.ai</code> / <code>admin123</code>
            </div>

            <p class="redirect-notice" id="redirectNotice">
                🔐 Upon authentication, you will be securely redirected back to your connected AI model client with an OAuth authorization token.
            </p>
        </div>
    </div>

    <script>
        const models = {models_json};
        const currentClientId = "{client_id}";
        const currentRedirectUri = "{safe_redirect}";
        const currentState = "{state}";
        let selectedModel = "{ai_model}" || "claude";

        // Render models list
        function renderModels() {{
            const container = document.getElementById('modelsList');
            container.innerHTML = '';
            models.forEach(m => {{
                const isSel = m.id === selectedModel;
                const card = document.createElement('div');
                card.className = `model-card ${{isSel ? 'selected' : ''}}`;
                card.onclick = () => selectModel(m.id);
                card.innerHTML = `
                    <span class="model-icon">${{m.icon}}</span>
                    <div>
                        <div class="model-name">${{m.name}}</div>
                        <div class="model-provider">${{m.provider}} (${{m.transport}})</div>
                    </div>
                `;
                container.appendChild(card);
            }});
        }}

        function selectModel(id) {{
            selectedModel = id;
            renderModels();
            const btnText = document.getElementById('tabSignupBtn').classList.contains('active') ? 
                `Sign Up & Connect to ${{getModelName(id)}}` : 
                `Log In & Connect to ${{getModelName(id)}}`;
            document.getElementById('signupSubmitBtn').innerText = btnText;
            document.getElementById('loginSubmitBtn').innerText = btnText;
        }}

        function getModelName(id) {{
            const m = models.find(x => x.id === id);
            return m ? m.name.split('/')[0] : 'AI';
        }}

        function switchTab(mode) {{
            const signupTab = document.getElementById('tabSignupBtn');
            const loginTab = document.getElementById('tabLoginBtn');
            const signupForm = document.getElementById('signupForm');
            const loginForm = document.getElementById('loginForm');
            hideAlert();

            if (mode === 'signup') {{
                signupTab.classList.add('active');
                loginTab.classList.remove('active');
                signupForm.style.display = 'block';
                loginForm.style.display = 'none';
            }} else {{
                loginTab.classList.add('active');
                signupTab.classList.remove('active');
                loginForm.style.display = 'block';
                signupForm.style.display = 'none';
            }}
            selectModel(selectedModel);
        }}

        function showAlert(msg, isError = true) {{
            const box = document.getElementById('alertBox');
            box.style.display = 'block';
            box.className = `alert-box ${{isError ? 'alert-error' : 'alert-success'}}`;
            box.innerText = msg;
        }}

        function hideAlert() {{
            document.getElementById('alertBox').style.display = 'none';
        }}

        async function handleSignup(e) {{
            e.preventDefault();
            hideAlert();
            const name = document.getElementById('signupName').value;
            const email = document.getElementById('signupEmail').value;
            const password = document.getElementById('signupPassword').value;

            try {{
                const res = await fetch('/auth/signup', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{
                        name, email, password,
                        client_id: currentClientId,
                        redirect_uri: currentRedirectUri,
                        state: currentState
                    }})
                }});
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Signup failed');

                showAlert('✅ Registration successful! Redirecting to connected AI...', false);
                sessionStorage.setItem('sumo_token', data.token);

                setTimeout(() => {{
                    if (data.redirect_url) {{
                        window.location.href = data.redirect_url;
                    }} else {{
                        window.location.href = '/ai-hub';
                    }}
                }}, 1200);
            }} catch (err) {{
                showAlert(err.message, true);
            }}
        }}

        async function handleLogin(e) {{
            e.preventDefault();
            hideAlert();
            const email = document.getElementById('loginEmail').value;
            const password = document.getElementById('loginPassword').value;

            try {{
                const res = await fetch('/auth/login', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{
                        email, password,
                        client_id: currentClientId,
                        redirect_uri: currentRedirectUri,
                        state: currentState
                    }})
                }});
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Login failed');

                showAlert('✅ Authenticated successfully! Redirecting to connected AI...', false);
                sessionStorage.setItem('sumo_token', data.token);

                setTimeout(() => {{
                    if (data.redirect_url) {{
                        window.location.href = data.redirect_url;
                    }} else {{
                        window.location.href = '/ai-hub';
                    }}
                }}, 1200);
            }} catch (err) {{
                showAlert(err.message, true);
            }}
        }}

        renderModels();
        selectModel(selectedModel);
    </script>
</body>
</html>"""
    return HTMLResponse(content=html)


@app.get("/auth/success", response_class=HTMLResponse)
async def auth_success_page(code: Optional[str] = "", state: Optional[str] = ""):
    """Fallback success page when redirect_uri is default."""
    return HTMLResponse(content=f"""<!DOCTYPE html>
<html>
<head>
    <title>SUMO AI MCP – Authorization Complete</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700&family=JetBrains+Mono&display=swap" rel="stylesheet">
    <style>
        body {{
            background: #0a0e17;
            color: #f8fafc;
            font-family: 'Outfit', sans-serif;
            display: flex;
            align-items: center;
            justify-content: center;
            height: 100vh;
            margin: 0;
        }}
        .card {{
            background: rgba(18, 24, 38, 0.85);
            border: 1px solid rgba(52, 211, 153, 0.4);
            border-radius: 20px;
            padding: 36px;
            max-width: 520px;
            text-align: center;
            box-shadow: 0 20px 40px rgba(0,0,0,0.5);
        }}
        h2 {{ color: #34d399; margin-bottom: 12px; }}
        p {{ color: #94a3b8; line-height: 1.5; margin-bottom: 20px; }}
        code {{
            background: #050811;
            padding: 8px 14px;
            border-radius: 8px;
            font-family: 'JetBrains Mono', monospace;
            color: #38bdf8;
            font-size: 0.9rem;
            display: block;
            word-break: break-all;
            margin-bottom: 20px;
        }}
        a {{
            display: inline-block;
            background: #0284c7;
            color: white;
            text-decoration: none;
            padding: 12px 24px;
            border-radius: 10px;
            font-weight: 600;
        }}
    </style>
</head>
<body>
    <div class="card">
        <h2>🎉 AI Model Authorized Successfully!</h2>
        <p>Your AI client has been linked to the SUMO MCP Simulation Server. Authorization code issued:</p>
        <code>{code or 'AUTH_TOKEN_ACTIVE'}</code>
        <a href="/ai-hub">Launch Interactive AI Hub</a>
    </div>
</body>
</html>""")


if __name__ == "__main__":
    import uvicorn
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    print(f"🚀 Starting SUMO AI MCP Auth & Redirect Gateway on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)
