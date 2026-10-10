"""
FUHX IP Verify — single WSGI entrypoint for Vercel.

Vercel CLI 57+ আর পুরনো "api/*.py per-file function" system support করে না —
exactly ONE Python entrypoint লাগে, pyproject.toml-এ declare করা:
    [tool.vercel]
    entrypoint = "api.index:app"
আর entrypoint-টা WSGI বা ASGI app হতে হবে (BaseHTTPRequestHandler class না)।

Routes:
  POST /api/verify  -> device fingerprint verification
  GET  /api/link    -> per-user signed link generator
  GET  /api/health  -> config status
  anything else     -> 404 JSON (static pages serve করে Vercel নিজে)
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import verify as verify_mod
import link as link_mod
import health as health_mod

MAX_BODY = 300_000


def _status_text(code):
    return {200: "OK", 400: "Bad Request", 403: "Forbidden",
            404: "Not Found", 405: "Method Not Allowed",
            500: "Internal Server Error"}.get(code, "OK")


def _json(start_response, code, obj):
    body = json.dumps(obj, ensure_ascii=False).encode()
    start_response(
        f"{code} {_status_text(code)}",
        [("Content-Type", "application/json; charset=utf-8"),
         ("Content-Length", str(len(body)))])
    return [body]


def _client_ip(environ):
    fwd = environ.get("HTTP_X_FORWARDED_FOR", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return environ.get("REMOTE_ADDR", "unknown")


def _read_body(environ):
    try:
        length = int(environ.get("CONTENT_LENGTH") or 0)
    except (TypeError, ValueError):
        length = 0
    if length <= 0 or length > MAX_BODY:
        return None
    return environ["wsgi.input"].read(length)


def _handle_verify(environ, start_response):
    if environ.get("REQUEST_METHOD") != "POST":
        return _json(start_response, 405,
                     {"ok": False, "error": "POST only"})
    raw = _read_body(environ)
    if raw is None:
        return _json(start_response, 400,
                     {"ok": False, "error": "bad body"})
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        return _json(start_response, 400,
                     {"ok": False, "error": "invalid json"})
    code, result = verify_mod.process_request(payload, _client_ip(environ))
    return _json(start_response, code, result)


def _handle_link(environ, start_response):
    if environ.get("REQUEST_METHOD") != "GET":
        return _json(start_response, 405,
                     {"ok": False, "error": "GET only"})
    qs = environ.get("QUERY_STRING", "")
    host = environ.get("HTTP_HOST", "")
    proto = environ.get("HTTP_X_FORWARDED_PROTO", "https")
    code, result = link_mod.process_request(qs, host, proto)
    return _json(start_response, code, result)


def _handle_health(environ, start_response):
    return _json(start_response, 200, health_mod.get_info())


def app(environ, start_response):
    """WSGI application — Vercel-এর declared entrypoint."""
    path = (environ.get("PATH_INFO") or "").rstrip("/") or "/"
    if path == "/api/verify":
        return _handle_verify(environ, start_response)
    if path == "/api/link":
        return _handle_link(environ, start_response)
    if path == "/api/health":
        return _handle_health(environ, start_response)
    return _json(start_response, 404, {"ok": False, "error": "not found"})
