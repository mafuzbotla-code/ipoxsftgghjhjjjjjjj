"""
GET /api/link?uid=<telegram_id>&key=<WEBHOOK_SECRET>

Per-user signed verify link generator.
যেকোনো bot এই endpoint-এ call করে user-specific link নিতে পারে —
bot-এর নিজের HMAC code লাগে না, শুধু key জানলেই হবে।

Response: {"ok": true, "uid": "123", "link": "https://<host>/verify?uid=123&t=..&sig=..", "expires_in": 86400}
"""
import hashlib
import hmac
import json
import os
import time
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
LINK_TTL = 24 * 3600  # link valid 24h


def sign_link(uid, t):
    msg = f"{uid}.{t}".encode()
    return hmac.new(WEBHOOK_SECRET.encode(), msg, hashlib.sha256).hexdigest()


# NOTE: shared by the WSGI entrypoint (api/index.py).
# Returns (http_code, response_dict).
def process_request(query_string, host, proto="https"):
    q = parse_qs(query_string)
    uid = (q.get("uid") or [""])[0].strip()
    key = (q.get("key") or [""])[0]

    if not WEBHOOK_SECRET:
        return 500, {"ok": False,
                     "error": "WEBHOOK_SECRET not configured on server"}
    if not key or not hmac.compare_digest(key, WEBHOOK_SECRET):
        return 403, {"ok": False, "error": "bad key"}
    if not uid or not uid.isdigit():
        return 400, {"ok": False,
                     "error": "uid required (numeric telegram id)"}
    if not host:
        return 500, {"ok": False, "error": "no host header"}

    t = int(time.time())
    sig = sign_link(uid, str(t))
    link = f"{proto}://{host}/verify?uid={uid}&t={t}&sig={sig}"
    return 200, {"ok": True, "uid": uid, "link": link,
                 "expires_in": LINK_TTL}


class handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        query_string = urlparse(self.path).query
        host = self.headers.get("host", "")
        proto = self.headers.get("x-forwarded-proto", "https")
        code, result = process_request(query_string, host, proto)
        self._send(code, result)

    def log_message(self, *args):
        pass
