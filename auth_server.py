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
import sumo_server
import ai_router

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

class SimulationRunRequest(BaseModel):
    bbox: str
    trips: Optional[int] = 600
    duration: Optional[int] = 7200
    density: Optional[str] = "medium"
    launch_gui: Optional[bool] = False

class AiChatRequest(BaseModel):
    model: Optional[str] = "builtin"
    prompt: str
    api_key: Optional[str] = None
    simulation_data: Optional[Dict[str, Any]] = None



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
# SIMULATION & MULTI-AI MODEL ORCHESTRATION ENDPOINTS
# =============================================================================

@app.post("/api/simulation/run")
async def run_simulation_api(req: SimulationRunRequest):
    """
    Direct Simulation Execution API for AI Models & Web Hub.
    Executes the SUMO simulation pipeline with security validation and parameter bounding.
    """
    safe_bbox = security_utils.sanitize_location_query(req.bbox)
    safe_trips, safe_duration, safe_density = security_utils.clamp_simulation_parameters(
        trips=req.trips or 600,
        duration=req.duration or 7200,
        density=req.density
    )

    security_utils.logger.info(
        f"Simulation triggered via API: bbox='{safe_bbox}', trips={safe_trips}, duration={safe_duration}, density='{safe_density}'"
    )

    result = sumo_server.run_full_simulation(
        bbox=safe_bbox,
        trips=safe_trips,
        duration=safe_duration,
        density=safe_density,
        launch_gui=req.launch_gui or False
    )

    return result


@app.post("/api/ai/chat")
async def ai_chat_api(req: AiChatRequest):
    """
    Multi-AI Model Chat & Traffic Engineering Reasoning API.
    Routes prompt and simulation telemetry to the selected AI model (Gemini, Claude, GPT-4, Ollama, Built-in).
    """
    try:
        response = ai_router.query_ai_model(
            model=req.model or "builtin",
            prompt=req.prompt,
            simulation_data=req.simulation_data,
            api_key=req.api_key
        )
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI query failed: {str(e)}")



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


# =============================================================================
# INTERACTIVE MULTI-AI TRAFFIC SIMULATION STUDIO (/ai-hub)
# =============================================================================

@app.get("/ai-hub", response_class=HTMLResponse)
async def ai_hub_studio():
    """
    State-of-the-art interactive Multi-AI Model Studio for SUMO Simulation & Analytics.
    Supports Google Gemini, Anthropic Claude, OpenAI GPT-4o, Ollama, and Built-in Expert Agent.
    """
    html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SUMO AI MCP – Multi-AI Traffic Simulation Studio</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-base: #070a12;
            --bg-card: rgba(16, 22, 35, 0.78);
            --bg-inner: rgba(10, 14, 24, 0.7);
            --border: rgba(255, 255, 255, 0.08);
            --border-glow: rgba(56, 189, 248, 0.28);
            --accent-cyan: #38bdf8;
            --accent-purple: #a855f7;
            --accent-green: #34d399;
            --accent-amber: #fbbf24;
            --accent-red: #f87171;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --gradient-brand: linear-gradient(135deg, #38bdf8 0%, #818cf8 50%, #c084fc 100%);
            --gradient-accent: linear-gradient(135deg, #0284c7 0%, #4f46e5 100%);
        }

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: 'Outfit', sans-serif;
        }

        body {
            background-color: var(--bg-base);
            color: var(--text-main);
            min-height: 100vh;
            padding: 24px 32px;
            background-image: 
                radial-gradient(circle at 10% 15%, rgba(56, 189, 248, 0.08) 0%, transparent 40%),
                radial-gradient(circle at 90% 85%, rgba(168, 85, 247, 0.08) 0%, transparent 40%);
            background-attachment: fixed;
        }

        /* Top Navigation Header */
        header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            background: var(--bg-card);
            backdrop-filter: blur(20px);
            border: 1px solid var(--border);
            border-radius: 20px;
            padding: 16px 28px;
            margin-bottom: 24px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.4);
        }

        .brand-box {
            display: flex;
            align-items: center;
            gap: 14px;
        }

        .brand-icon {
            font-size: 1.8rem;
            background: rgba(56, 189, 248, 0.12);
            padding: 10px;
            border-radius: 14px;
            border: 1px solid rgba(56, 189, 248, 0.3);
        }

        .brand-title {
            font-size: 1.45rem;
            font-weight: 800;
            background: var(--gradient-brand);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .brand-tag {
            font-size: 0.75rem;
            color: var(--text-muted);
            letter-spacing: 0.5px;
        }

        .nav-links {
            display: flex;
            align-items: center;
            gap: 14px;
        }

        .status-pill {
            display: flex;
            align-items: center;
            gap: 8px;
            background: rgba(52, 211, 153, 0.1);
            border: 1px solid rgba(52, 211, 153, 0.3);
            border-radius: 9999px;
            padding: 6px 14px;
            font-size: 0.8rem;
            font-weight: 600;
            color: var(--accent-green);
        }

        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: var(--accent-green);
            box-shadow: 0 0 10px var(--accent-green);
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.4; transform: scale(0.9); }
            100% { opacity: 1; transform: scale(1); }
        }

        .nav-btn {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--border);
            color: var(--text-main);
            padding: 8px 16px;
            border-radius: 12px;
            text-decoration: none;
            font-size: 0.85rem;
            font-weight: 600;
            transition: all 0.2s;
        }

        .nav-btn:hover {
            background: rgba(56, 189, 248, 0.15);
            border-color: var(--accent-cyan);
            color: var(--accent-cyan);
        }

        /* AI Model Selector Toolbar */
        .model-toolbar {
            display: flex;
            align-items: center;
            gap: 12px;
            background: var(--bg-card);
            backdrop-filter: blur(16px);
            border: 1px solid var(--border);
            border-radius: 18px;
            padding: 12px 16px;
            margin-bottom: 24px;
            overflow-x: auto;
        }

        .model-tab {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 10px 18px;
            border-radius: 12px;
            border: 1px solid transparent;
            background: transparent;
            color: var(--text-muted);
            font-size: 0.92rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
            white-space: nowrap;
        }

        .model-tab:hover {
            color: var(--text-main);
            background: rgba(255, 255, 255, 0.04);
        }

        .model-tab.active {
            color: var(--text-main);
            background: rgba(56, 189, 248, 0.15);
            border-color: var(--accent-cyan);
            box-shadow: 0 0 15px rgba(56, 189, 248, 0.2);
        }

        /* Main Workspace Grid */
        .workspace-grid {
            display: grid;
            grid-template-columns: 380px 1fr;
            gap: 24px;
        }

        @media (max-width: 1040px) {
            .workspace-grid {
                grid-template-columns: 1fr;
            }
        }

        /* Left Column: Control Panel */
        .control-panel {
            background: var(--bg-card);
            backdrop-filter: blur(18px);
            border: 1px solid var(--border);
            border-radius: 20px;
            padding: 24px;
            display: flex;
            flex-direction: column;
            gap: 20px;
        }

        .panel-heading {
            font-size: 1.15rem;
            font-weight: 700;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .panel-heading span.badge {
            font-size: 0.72rem;
            padding: 3px 8px;
            border-radius: 6px;
            background: rgba(56, 189, 248, 0.12);
            color: var(--accent-cyan);
        }

        .form-group {
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        .form-label {
            font-size: 0.85rem;
            font-weight: 600;
            color: var(--text-muted);
            display: flex;
            justify-content: space-between;
        }

        .form-input {
            width: 100%;
            background: var(--bg-inner);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 12px 14px;
            color: var(--text-main);
            font-size: 0.92rem;
            transition: all 0.2s;
        }

        .form-input:focus {
            outline: none;
            border-color: var(--accent-cyan);
            box-shadow: 0 0 12px rgba(56, 189, 248, 0.2);
        }

        /* Preset Chips */
        .chips-container {
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            margin-top: 4px;
        }

        .preset-chip {
            font-size: 0.75rem;
            font-weight: 500;
            padding: 4px 10px;
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid var(--border);
            color: var(--text-muted);
            cursor: pointer;
            transition: all 0.15s;
        }

        .preset-chip:hover {
            background: rgba(56, 189, 248, 0.12);
            border-color: var(--accent-cyan);
            color: var(--accent-cyan);
        }

        /* Slider Controls */
        .range-slider {
            width: 100%;
            accent-color: var(--accent-cyan);
        }

        /* Density Button Group */
        .density-btn-group {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 6px;
        }

        .density-btn {
            padding: 8px 4px;
            border-radius: 8px;
            border: 1px solid var(--border);
            background: var(--bg-inner);
            color: var(--text-muted);
            font-size: 0.8rem;
            font-weight: 600;
            text-align: center;
            cursor: pointer;
            transition: all 0.2s;
        }

        .density-btn:hover {
            color: var(--text-main);
            border-color: var(--accent-cyan);
        }

        .density-btn.active {
            background: rgba(56, 189, 248, 0.15);
            border-color: var(--accent-cyan);
            color: var(--accent-cyan);
        }

        /* Launch Button */
        .launch-btn {
            background: var(--gradient-accent);
            color: white;
            border: none;
            border-radius: 14px;
            padding: 16px;
            font-size: 1rem;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.25s ease;
            box-shadow: 0 10px 25px -5px rgba(2, 132, 199, 0.4);
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
        }

        .launch-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 15px 30px -5px rgba(2, 132, 199, 0.6);
        }

        .launch-btn:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: none;
        }

        /* Right Column: Analytics & AI Audit */
        .results-col {
            display: flex;
            flex-direction: column;
            gap: 24px;
        }

        /* KPI Cards Grid */
        .kpi-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 16px;
        }

        .kpi-card {
            background: var(--bg-card);
            backdrop-filter: blur(16px);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 18px;
            display: flex;
            flex-direction: column;
            gap: 8px;
            transition: transform 0.2s;
        }

        .kpi-card:hover {
            border-color: var(--border-glow);
            transform: translateY(-2px);
        }

        .kpi-label {
            font-size: 0.78rem;
            font-weight: 600;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .kpi-value {
            font-size: 1.75rem;
            font-weight: 800;
            font-family: 'JetBrains Mono', monospace;
            color: var(--text-main);
        }

        .kpi-sub {
            font-size: 0.76rem;
            color: var(--text-muted);
        }

        .los-badge {
            display: inline-flex;
            align-items: center;
            padding: 4px 10px;
            border-radius: 6px;
            font-weight: 700;
            font-size: 0.85rem;
            width: fit-content;
        }

        .los-a { background: rgba(52, 211, 153, 0.2); color: #34d399; border: 1px solid #34d399; }
        .los-b { background: rgba(56, 189, 248, 0.2); color: #38bdf8; border: 1px solid #38bdf8; }
        .los-c { background: rgba(251, 191, 36, 0.2); color: #fbbf24; border: 1px solid #fbbf24; }
        .los-d { background: rgba(249, 115, 22, 0.2); color: #f97316; border: 1px solid #f97316; }
        .los-e { background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid #f87171; }
        .los-f { background: rgba(220, 38, 38, 0.3); color: #ef4444; border: 1px solid #dc2626; }

        /* Vehicle Modal Split Card */
        .vtypes-card {
            background: var(--bg-card);
            backdrop-filter: blur(16px);
            border: 1px solid var(--border);
            border-radius: 18px;
            padding: 20px 24px;
        }

        .vtypes-header {
            font-size: 0.95rem;
            font-weight: 700;
            margin-bottom: 14px;
            display: flex;
            justify-content: space-between;
        }

        .vtypes-bars {
            display: flex;
            flex-direction: column;
            gap: 10px;
        }

        .vtype-row {
            display: grid;
            grid-template-columns: 130px 1fr 60px;
            align-items: center;
            gap: 12px;
            font-size: 0.85rem;
        }

        .vtype-bar-bg {
            background: rgba(255, 255, 255, 0.06);
            border-radius: 9999px;
            height: 8px;
            overflow: hidden;
        }

        .vtype-bar-fill {
            height: 100%;
            border-radius: 9999px;
            transition: width 0.6s ease;
        }

        /* AI Reasoning Terminal */
        .ai-terminal {
            background: var(--bg-card);
            backdrop-filter: blur(18px);
            border: 1px solid var(--border);
            border-radius: 20px;
            padding: 24px;
            display: flex;
            flex-direction: column;
            gap: 16px;
        }

        .terminal-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            border-bottom: 1px solid var(--border);
            padding-bottom: 12px;
        }

        .terminal-title {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 1rem;
            font-weight: 700;
        }

        .terminal-output {
            background: var(--bg-inner);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 20px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.88rem;
            line-height: 1.6;
            color: #cbd5e1;
            min-height: 220px;
            max-height: 400px;
            overflow-y: auto;
            white-space: pre-wrap;
        }

        .chat-input-box {
            display: flex;
            gap: 10px;
        }

        .chat-input {
            flex: 1;
            background: var(--bg-inner);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 12px 16px;
            color: var(--text-main);
            font-size: 0.92rem;
        }

        .chat-input:focus {
            outline: none;
            border-color: var(--accent-cyan);
        }

        .send-btn {
            background: var(--accent-cyan);
            color: #070a12;
            border: none;
            border-radius: 12px;
            padding: 0 20px;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.2s;
        }

        .send-btn:hover {
            background: #7dd3fc;
        }
    </style>
</head>
<body>

    <!-- Header -->
    <header>
        <div class="brand-box">
            <div class="brand-icon">🚦</div>
            <div>
                <h1 class="brand-title">SUMO AI MCP Studio</h1>
                <div class="brand-tag">Intelligent Urban Traffic Simulation & Multi-AI Orchestrator</div>
            </div>
        </div>
        <div class="nav-links">
            <div class="status-pill">
                <div class="status-dot"></div>
                <span id="activeModelBadge">Connected: Built-in Expert</span>
            </div>
            <a href="/auth/portal" class="nav-btn">🔐 Auth / Signup</a>
            <a href="/auth/models" class="nav-btn" target="_blank">📋 AI Specs</a>
        </div>
    </header>

    <!-- AI Model Selection Bar -->
    <div class="model-toolbar">
        <button class="model-tab active" onclick="selectAiModel('builtin')">
            <span>⚡</span> Built-in SUMO Agent
        </button>
        <button class="model-tab" onclick="selectAiModel('gemini')">
            <span>🔵</span> Google Gemini 1.5
        </button>
        <button class="model-tab" onclick="selectAiModel('claude')">
            <span>🟣</span> Anthropic Claude 3.5
        </button>
        <button class="model-tab" onclick="selectAiModel('gpt4')">
            <span>🟢</span> OpenAI GPT-4o
        </button>
        <button class="model-tab" onclick="selectAiModel('ollama')">
            <span>🦙</span> Ollama Local
        </button>
    </div>

    <!-- Workspace -->
    <div class="workspace-grid">
        <!-- Control Panel -->
        <div class="control-panel">
            <div class="panel-heading">
                <span>Simulation Parameters</span>
                <span class="badge">Microscopic SUMO 1.18+</span>
            </div>

            <!-- Corridor / Place Input -->
            <div class="form-group">
                <label class="form-label">
                    <span>Corridor / Neighborhood / BBox</span>
                </label>
                <input type="text" id="simLocation" class="form-input" value="Chennai" placeholder="e.g. Gandhipuram, Chennai, 76.89,10.89,76.91,10.91">
                <div class="chips-container">
                    <span class="preset-chip" onclick="setPreset('Chennai')">Chennai</span>
                    <span class="preset-chip" onclick="setPreset('Gandhipuram')">Gandhipuram</span>
                    <span class="preset-chip" onclick="setPreset('Ettimadai')">Ettimadai</span>
                    <span class="preset-chip" onclick="setPreset('Peelamedu')">Peelamedu</span>
                    <span class="preset-chip" onclick="setPreset('Bangalore')">Bangalore</span>
                    <span class="preset-chip" onclick="setPreset('Delhi')">Delhi</span>
                </div>
            </div>

            <!-- Trips Slider -->
            <div class="form-group">
                <label class="form-label">
                    <span>Total Generated Trips</span>
                    <span id="tripsValue" style="color: var(--accent-cyan); font-family: monospace;">600</span>
                </label>
                <input type="range" id="tripsSlider" class="range-slider" min="100" max="2500" step="50" value="600" oninput="updateSliderVal('tripsSlider', 'tripsValue')">
            </div>

            <!-- Duration Slider -->
            <div class="form-group">
                <label class="form-label">
                    <span>Simulation Duration</span>
                    <span id="durValue" style="color: var(--accent-cyan); font-family: monospace;">7200s (2 hrs)</span>
                </label>
                <input type="range" id="durSlider" class="range-slider" min="1800" max="14400" step="600" value="7200" oninput="updateDurationVal()">
            </div>

            <!-- Density Buttons -->
            <div class="form-group">
                <label class="form-label">Traffic Density Profile</label>
                <div class="density-btn-group">
                    <button class="density-btn" onclick="setDensity('low', this)">Low</button>
                    <button class="density-btn active" onclick="setDensity('medium', this)">Med</button>
                    <button class="density-btn" onclick="setDensity('high', this)">High</button>
                    <button class="density-btn" onclick="setDensity('congested', this)">Congested</button>
                </div>
            </div>

            <!-- Visual GUI checkbox -->
            <div class="form-group" style="flex-direction: row; align-items: center; gap: 10px;">
                <input type="checkbox" id="launchGuiCheck" style="accent-color: var(--accent-cyan); width: 18px; height: 18px;">
                <label for="launchGuiCheck" style="font-size: 0.85rem; color: var(--text-muted); cursor: pointer;">
                    Launch Desktop SUMO GUI Window
                </label>
            </div>

            <!-- Launch Simulation Button -->
            <button id="runSimBtn" class="launch-btn" onclick="executeSimulation()">
                <span>🚀 Run Full Microscopic Simulation</span>
            </button>
        </div>

        <!-- Right Side: Analytics KPIs & AI Terminal -->
        <div class="results-col">
            <!-- KPIs -->
            <div class="kpi-grid">
                <div class="kpi-card">
                    <span class="kpi-label">Insertion Rate</span>
                    <span class="kpi-value" id="kpiInsertion">--%</span>
                    <span class="kpi-sub" id="kpiLoadedSub">Loaded: -- / Inserted: --</span>
                </div>
                <div class="kpi-card">
                    <span class="kpi-label">Average Speed</span>
                    <span class="kpi-value" id="kpiSpeed">-- km/h</span>
                    <span class="kpi-sub">Heterogeneous Indian mix</span>
                </div>
                <div class="kpi-card">
                    <span class="kpi-label">Average Delay</span>
                    <span class="kpi-value" id="kpiDelay">-- s</span>
                    <span class="kpi-sub">Time loss per completed trip</span>
                </div>
                <div class="kpi-card">
                    <span class="kpi-label">Level of Service</span>
                    <div id="kpiLosContainer" style="margin-top: 4px;">
                        <span class="los-badge los-b" id="kpiLos">LOS --</span>
                    </div>
                    <span class="kpi-sub" id="kpiCongestion">Congestion Index: --</span>
                </div>
            </div>

            <!-- Vehicle Distribution -->
            <div class="vtypes-card">
                <div class="vtypes-header">
                    <span>Heterogeneous Indian Traffic Distribution Breakdown</span>
                    <span style="font-size: 0.8rem; color: var(--accent-cyan);">Sublane Res: 0.8m</span>
                </div>
                <div class="vtypes-bars">
                    <div class="vtype-row">
                        <span>🏍️ Motorcycles</span>
                        <div class="vtype-bar-bg"><div class="vtype-bar-fill" style="width: 35%; background: #f87171;"></div></div>
                        <span style="font-family: monospace;">35%</span>
                    </div>
                    <div class="vtype-row">
                        <span>🛺 Auto-rickshaws</span>
                        <div class="vtype-bar-bg"><div class="vtype-bar-fill" style="width: 20%; background: #fbbf24;"></div></div>
                        <span style="font-family: monospace;">20%</span>
                    </div>
                    <div class="vtype-row">
                        <span>🚗 Passenger Cars</span>
                        <div class="vtype-bar-bg"><div class="vtype-bar-fill" style="width: 30%; background: #38bdf8;"></div></div>
                        <span style="font-family: monospace;">30%</span>
                    </div>
                    <div class="vtype-row">
                        <span>🚌 Public Transit</span>
                        <div class="vtype-bar-bg"><div class="vtype-bar-fill" style="width: 8%; background: #34d399;"></div></div>
                        <span style="font-family: monospace;">8%</span>
                    </div>
                    <div class="vtype-row">
                        <span>🚚 Freight Trucks</span>
                        <div class="vtype-bar-bg"><div class="vtype-bar-fill" style="width: 7%; background: #fb923c;"></div></div>
                        <span style="font-family: monospace;">7%</span>
                    </div>
                </div>
            </div>

            <!-- AI Reasoning Terminal -->
            <div class="ai-terminal">
                <div class="terminal-header">
                    <div class="terminal-title">
                        <span>🧠</span>
                        <span id="terminalModelTitle">AI Traffic Engineering Reasoning</span>
                    </div>
                    <span style="font-size: 0.78rem; color: var(--text-muted); font-family: monospace;" id="execStatus">Status: Idle</span>
                </div>
                <div class="terminal-output" id="terminalOutput">Welcome to the SUMO AI Simulation Studio!

1. Select your desired AI model from the toolbar above (Gemini, Claude, GPT-4, Ollama, or Built-in).
2. Choose a city corridor (e.g., Chennai Central, Gandhipuram, Bangalore).
3. Click "Run Full Microscopic Simulation" to execute netconvert, route generation, and SUMO physics.
4. Your connected AI will inspect the telemetry, calculate Highway Capacity LOS, and recommend intersection optimizations.</div>

                <div class="chat-input-box">
                    <input type="text" id="aiChatInput" class="chat-input" placeholder="Ask your connected AI model about corridor bottlenecks, signal timing, or lane design..." onkeypress="if(event.key === 'Enter') sendAiChat()">
                    <button class="send-btn" onclick="sendAiChat()">Send</button>
                </div>
            </div>
        </div>
    </div>

    <script>
        let currentModel = 'builtin';
        let currentDensity = 'medium';
        let lastSimulationData = null;

        function selectAiModel(modelId) {
            currentModel = modelId;
            document.querySelectorAll('.model-tab').forEach(btn => btn.classList.remove('active'));
            event.currentTarget.classList.add('active');

            const names = {
                'builtin': 'Built-in Traffic Expert',
                'gemini': 'Google Gemini 1.5',
                'claude': 'Anthropic Claude 3.5 Sonnet',
                'gpt4': 'OpenAI GPT-4o',
                'ollama': 'Ollama Llama 3 Local'
            };
            document.getElementById('activeModelBadge').innerText = `Connected: ${names[modelId] || modelId}`;
            document.getElementById('terminalModelTitle').innerText = `${names[modelId] || modelId} Reasoning Stream`;
        }

        function setPreset(loc) {
            document.getElementById('simLocation').value = loc;
        }

        function updateSliderVal(sliderId, textId) {
            document.getElementById(textId).innerText = document.getElementById(sliderId).value;
        }

        function updateDurationVal() {
            const val = document.getElementById('durSlider').value;
            const hrs = (val / 3600).toFixed(1);
            document.getElementById('durValue').innerText = `${val}s (${hrs} hrs)`;
        }

        function setDensity(dens, el) {
            currentDensity = dens;
            document.querySelectorAll('.density-btn').forEach(b => b.classList.remove('active'));
            el.classList.add('active');
        }

        async function executeSimulation() {
            const location = document.getElementById('simLocation').value.trim();
            const trips = parseInt(document.getElementById('tripsSlider').value);
            const duration = parseInt(document.getElementById('durSlider').value);
            const launchGui = document.getElementById('launchGuiCheck').checked;
            const btn = document.getElementById('runSimBtn');
            const terminal = document.getElementById('terminalOutput');
            const statusLabel = document.getElementById('execStatus');

            if (!location) {
                alert('Please enter a location or coordinate bounding box');
                return;
            }

            btn.disabled = true;
            btn.innerHTML = '<span>⏳ Simulating Microscopic Traffic...</span>';
            statusLabel.innerText = 'Status: Executing SUMO Pipeline...';
            terminal.innerText = `[1/5] Geocoding & Downloading OpenStreetMap data for '${location}'...\n[2/5] Compiling SUMO Network (mymap.net.xml)...\n[3/5] Generating heterogeneous Indian trips & routes...\n[4/5] Executing headless SUMO physics...\n[5/5] Parsing stats.xml & tripinfo.xml...`;

            try {
                const res = await fetch('/api/simulation/run', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        bbox: location,
                        trips: trips,
                        duration: duration,
                        density: currentDensity,
                        launch_gui: launchGui
                    })
                });
                const data = await res.json();
                lastSimulationData = data;

                // Update Telemetry KPIs
                const loaded = data.analytics?.total_vehicles_loaded || 0;
                const inserted = data.analytics?.total_vehicles_inserted || 0;
                const rate = loaded > 0 ? ((inserted / loaded) * 100).toFixed(1) : '100.0';
                const speed = data.trip_details?.average_speed_kmh || 0.0;
                const delay = data.trip_details?.average_time_loss_s || 0.0;
                const cong = data.trip_details?.congestion_index || 0.0;

                document.getElementById('kpiInsertion').innerText = `${rate}%`;
                document.getElementById('kpiLoadedSub').innerText = `Loaded: ${loaded} / Inserted: ${inserted}`;
                document.getElementById('kpiSpeed').innerText = `${speed.toFixed(1)} km/h`;
                document.getElementById('kpiDelay').innerText = `${delay.toFixed(1)} s`;
                document.getElementById('kpiCongestion').innerText = `Congestion Index: ${cong.toFixed(4)}`;

                // Compute LOS
                let losClass = 'los-b';
                let losText = 'LOS B';
                if (delay < 10) { losClass = 'los-a'; losText = 'LOS A (Free)'; }
                else if (delay < 20) { losClass = 'los-b'; losText = 'LOS B (Stable)'; }
                else if (delay < 35) { losClass = 'los-c'; losText = 'LOS C (Fair)'; }
                else if (delay < 55) { losClass = 'los-d'; losText = 'LOS D (Dense)'; }
                else if (delay < 80) { losClass = 'los-e'; losText = 'LOS E (Unstable)'; }
                else { losClass = 'los-f'; losText = 'LOS F (Breakdown)'; }

                const losBadge = document.getElementById('kpiLos');
                losBadge.className = `los-badge ${losClass}`;
                losBadge.innerText = losText;

                // Request AI Engineering Analysis
                statusLabel.innerText = 'Status: Querying Connected AI Model...';
                const aiRes = await fetch('/api/ai/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        model: currentModel,
                        prompt: `Perform an in-depth urban traffic engineering audit for corridor '${location}' with ${trips} vehicles.`,
                        simulation_data: data
                    })
                });
                const aiData = await aiRes.json();
                terminal.innerText = aiData.response || JSON.stringify(aiData, null, 2);
                statusLabel.innerText = 'Status: Analysis Complete';
            } catch (err) {
                terminal.innerText = `❌ Error executing simulation: ${err.message}`;
                statusLabel.innerText = 'Status: Error';
            } finally {
                btn.disabled = false;
                btn.innerHTML = '<span>🚀 Run Full Microscopic Simulation</span>';
            }
        }

        async function sendAiChat() {
            const input = document.getElementById('aiChatInput');
            const prompt = input.value.trim();
            if (!prompt) return;

            const terminal = document.getElementById('terminalOutput');
            const statusLabel = document.getElementById('execStatus');
            input.value = '';
            terminal.innerText += `\n\n> User: ${prompt}\n\nThinking...`;
            statusLabel.innerText = 'Status: AI Answering...';

            try {
                const res = await fetch('/api/ai/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        model: currentModel,
                        prompt: prompt,
                        simulation_data: lastSimulationData
                    })
                });
                const data = await res.json();
                terminal.innerText += `\n${data.response || JSON.stringify(data, null, 2)}`;
                statusLabel.innerText = 'Status: Ready';
            } catch (err) {
                terminal.innerText += `\n❌ Error: ${err.message}`;
                statusLabel.innerText = 'Status: Error';
            }
        }
    </script>
</body>
</html>"""
    return HTMLResponse(content=html)


if __name__ == "__main__":
    import uvicorn
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    print(f"🚀 Starting SUMO AI MCP Auth & Redirect Gateway on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)

