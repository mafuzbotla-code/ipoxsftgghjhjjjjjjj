"""GET /api/health — config status (no secrets exposed)."""
import json
import os
from http.server import BaseHTTPRequestHandler


def get_info():
    """Shared by the WSGI entrypoint (api/index.py)."""
    return {
        "ok": True,
        "service": "FUHX IP Verify System",
        "webhook_configured": bool(os.environ.get("BOT_WEBHOOK_URL")),
        "secret_configured": bool(os.environ.get("WEBHOOK_SECRET")),
        "store": ("upstash"
                  if os.environ.get("UPSTASH_REDIS_REST_URL") else "file"),
    }


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps(get_info()).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass
