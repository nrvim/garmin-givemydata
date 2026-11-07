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
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.responses import Response

BASE_URL = os.environ.get("BASE_URL", "https://solid-palm-tree-5g74wjx94vq9hv5x7-8000.app.github.dev")
CODES = {}
TOKEN_FILE = Path(os.environ.get("GARMIN_DATA_DIR", ".")) / "oauth_tokens.json"


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
    code = secrets.token_hex(16)
    CODES[code] = {"redirect_uri": redirect_uri, "challenge": code_challenge, "client_id": client_id}
    sep = "&" if "?" in redirect_uri else "?"
    return RedirectResponse(f"{redirect_uri}{sep}code={code}&state={state}")


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
