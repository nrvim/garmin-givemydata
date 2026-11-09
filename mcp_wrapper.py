import base64
import hashlib
import json
import os
import secrets
import sys
import threading
import time

sys.path.insert(0, ".")
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.responses import Response

BASE_URL = os.environ.get("BASE_URL", "https://solid-palm-tree-5g74wjx94vq9hv5x7-8000.app.github.dev")
CODES = {}
TOKEN_FILE = Path(os.environ.get("GARMIN_DATA_DIR", ".")) / "oauth_tokens.json"
ENV_FILE = Path(os.environ.get("GARMIN_DATA_DIR", ".")) / ".env"


def load_password() -> str:
    """MCP_PASSWORD from the environment, or from the .env file next to the data."""
    if os.environ.get("MCP_PASSWORD"):
        return os.environ["MCP_PASSWORD"]
    try:
        for line in ENV_FILE.read_text().splitlines():
            key, _, value = line.strip().partition("=")
            if key.strip() == "MCP_PASSWORD":
                return value.strip()
    except Exception:
        pass
    return ""


MCP_PASSWORD = load_password()
if not MCP_PASSWORD:
    print(
        "WARNING: MCP_PASSWORD is not set - new connector logins are refused.\n"
        "         Add a line MCP_PASSWORD=<your password> to .env and restart.",
        flush=True,
    )


def load_tokens():
    try:
        if TOKEN_FILE.exists():
            data = json.loads(TOKEN_FILE.read_text())
            now = time.time()
            return {k: v for k, v in data.items() if v.get("expires", 0) > now}
    except Exception:
        pass
    return {}


def save_tokens(tokens):
    try:
        TOKEN_FILE.write_text(json.dumps(tokens))
    except Exception:
        pass


TOKENS = load_tokens()


def start_mcp():
    from garmin_mcp.server import mcp

    mcp.run(transport="sse", host="127.0.0.1", port=8001)


threading.Thread(target=start_mcp, daemon=True).start()
time.sleep(3)

app = FastAPI()


@app.get("/.well-known/oauth-authorization-server")
async def oauth_meta():
    return JSONResponse(
        {
            "issuer": BASE_URL,
            "authorization_endpoint": f"{BASE_URL}/oauth/authorize",
            "token_endpoint": f"{BASE_URL}/oauth/token",
            "registration_endpoint": f"{BASE_URL}/oauth/register",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code"],
            "code_challenge_methods_supported": ["S256"],
        }
    )


@app.get("/.well-known/oauth-protected-resource")
async def oauth_resource():
    return JSONResponse({"resource": BASE_URL, "authorization_servers": [BASE_URL]})


@app.post("/oauth/register")
async def register(request: Request):
    body = await request.json()
    client_id = secrets.token_hex(16)
    return JSONResponse({"client_id": client_id, "client_secret": "none", **body})


_LOGIN_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Garmin MCP</title>
<style>body{{font-family:system-ui,sans-serif;max-width:360px;margin:15vh auto;padding:0 16px}}
input,button{{width:100%;padding:12px;margin-top:10px;font-size:16px;box-sizing:border-box}}
.err{{color:#b00020}}</style></head><body>
<h2>Garmin MCP</h2><p>Voer het wachtwoord in om Claude toegang te geven.</p>{error}
<form method="post" action="/oauth/authorize">
<input type="hidden" name="redirect_uri" value="{redirect_uri}">
<input type="hidden" name="state" value="{state}">
<input type="hidden" name="client_id" value="{client_id}">
<input type="hidden" name="code_challenge" value="{code_challenge}">
<input type="password" name="password" placeholder="Wachtwoord" autofocus required>
<button type="submit">Toegang geven</button></form></body></html>"""

_FAILED_ATTEMPTS = []


def _login_page(redirect_uri, state, client_id, code_challenge, error=""):
    from html import escape

    if not MCP_PASSWORD:
        error = '<p class="err">Server heeft geen MCP_PASSWORD ingesteld; inloggen is uitgeschakeld.</p>'
    return HTMLResponse(
        _LOGIN_PAGE.format(
            error=error,
            redirect_uri=escape(redirect_uri),
            state=escape(state),
            client_id=escape(client_id),
            code_challenge=escape(code_challenge),
        )
    )


@app.get("/oauth/authorize")
async def authorize(
    request: Request,
    response_type: str = "",
    client_id: str = "",
    redirect_uri: str = "",
    state: str = "",
    code_challenge: str = "",
    code_challenge_method: str = "",
):
    return _login_page(redirect_uri, state, client_id, code_challenge)


@app.post("/oauth/authorize")
async def authorize_submit(
    password: str = Form(""),
    client_id: str = Form(""),
    redirect_uri: str = Form(""),
    state: str = Form(""),
    code_challenge: str = Form(""),
):
    # Slow down guessing: at most 5 failed attempts per 10 minutes
    now = time.time()
    _FAILED_ATTEMPTS[:] = [t for t in _FAILED_ATTEMPTS if now - t < 600]
    if len(_FAILED_ATTEMPTS) >= 5:
        return HTMLResponse("Te veel pogingen. Probeer het over 10 minuten opnieuw.", status_code=429)
    if not MCP_PASSWORD or not secrets.compare_digest(password.encode(), MCP_PASSWORD.encode()):
        _FAILED_ATTEMPTS.append(now)
        return _login_page(redirect_uri, state, client_id, code_challenge, '<p class="err">Onjuist wachtwoord.</p>')
    code = secrets.token_hex(16)
    CODES[code] = {"redirect_uri": redirect_uri, "challenge": code_challenge, "client_id": client_id}
    from urllib.parse import urlencode

    sep = "&" if "?" in redirect_uri else "?"
    query = urlencode({"code": code, "state": state})
    return RedirectResponse(f"{redirect_uri}{sep}{query}", status_code=303)


@app.post("/oauth/token")
async def token_ep(
    request: Request,
    grant_type: str = Form(""),
    code: str = Form(""),
    redirect_uri: str = Form(""),
    code_verifier: str = Form(""),
    client_id: str = Form(""),
):
    if code not in CODES:
        return JSONResponse({"error": "invalid_grant"}, status_code=400)
    stored = CODES[code]
    if stored.get("challenge") and code_verifier:
        digest = hashlib.sha256(code_verifier.encode()).digest()
        expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
        if expected != stored["challenge"]:
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
    access_token = secrets.token_hex(32)
    TOKENS[access_token] = {"client_id": client_id, "expires": time.time() + 86400 * 30}
    save_tokens(TOKENS)
    del CODES[code]
    return JSONResponse({"access_token": access_token, "token_type": "bearer", "expires_in": 86400 * 30})


@app.get("/health")
async def health():
    return {"status": "ok", "tokens": len(TOKENS)}


def check_token(request: Request):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return False
    record = TOKENS.get(auth[7:].strip())
    return record and record["expires"] > time.time()


@app.get("/sse")
async def sse_proxy(request: Request):
    if not check_token(request):
        return Response(json.dumps({"error": "unauthorized"}), status_code=401, media_type="application/json")
    from starlette.responses import StreamingResponse

    async def stream():
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("GET", "http://127.0.0.1:8001/sse") as r:
                async for chunk in r.aiter_bytes():
                    yield chunk

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.post("/messages/")
@app.post("/messages")
async def messages_proxy(request: Request):
    if not check_token(request):
        return Response(json.dumps({"error": "unauthorized"}), status_code=401, media_type="application/json")
    body = await request.body()
    params = request.url.query
    url = "http://127.0.0.1:8001/messages/" + (f"?{params}" if params else "")
    async with httpx.AsyncClient() as client:
        r = await client.post(
            url,
            content=body,
            headers={k: v for k, v in request.headers.items() if k.lower() not in ["host", "authorization"]},
        )
    return Response(r.content, status_code=r.status_code, media_type=r.headers.get("content-type", "application/json"))


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
