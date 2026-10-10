"""
FUHX IP Verify System — Vercel serverless API (/api/verify)

Flow:
  1. Telegram bot দেয় user-কে signed link: /verify?uid=<tg_id>&t=<ts>&sig=<hmac>
  2. Browser page JS দিয়ে MAXIMUM device signal collect করে POST করে এখানে
     (canvas+GPU+audio fingerprint, fonts, voices, phone model, screen, CPU/RAM...)
  3. Two-tier device matching:
       Tier 1 (exact): full stable fingerprint SHA-256
       Tier 2 (fuzzy): 10 high-entropy component-এর >=8 টা মিললেই same device
                       (browser update-এ ছোট field বদলালেও ধরা পড়ে —
                        "জীবনেও দ্বিতীয়বার verify" বন্ধ করতে)
  4. নতুন device -> save, status=success, webhook -> bot ("verified")
     same device + অন্য uid -> strike+1 -> rejected (warning 1,2) / blocked (3)

Storage: Upstash Redis (env থাকলে, permanent) নাহলে JSON file (/tmp on Vercel,
local-এ ./data/devices.json). Vercel-এর filesystem ephemeral — permanent data-র
জন্য Upstash (free) ব্যবহার করো, README দেখো.
"""
import hashlib
import hmac
import json
import os
import secrets
import time
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler

# ---------------------------------------------------------------- config
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
BOT_WEBHOOK_URL = os.environ.get("BOT_WEBHOOK_URL", "")
UPSTASH_URL = os.environ.get("UPSTASH_REDIS_REST_URL", "").rstrip("/")
UPSTASH_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")
DATA_KEY = "fuhx:devices:v1"
LINK_TTL = 24 * 3600          # verify link valid 24h
MAX_STRIKES = 3               # 3 warning-এর পর block
FUZZY_THRESHOLD = 8           # 10 component-এর 8 টা মিললেই same device


def utcnow_iso():
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------- storage
class FileStore:
    def __init__(self, path):
        self.path = path

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                d = json.load(f)
                d.setdefault("devices", {})
                return d
        except Exception:
            return {"devices": {}}

    def save(self, data):
        folder = os.path.dirname(self.path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, self.path)


class UpstashStore:
    """Upstash Redis REST (Vercel marketplace, free tier) — permanent storage."""

    def __init__(self, url, token):
        self.url = url
        self.token = token

    def _call(self, *cmd):
        body = json.dumps(list(cmd)).encode()
        req = urllib.request.Request(
            self.url, data=body,
            headers={"Authorization": f"Bearer {self.token}",
                     "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode())

    def load(self):
        try:
            res = self._call("GET", DATA_KEY)
            val = res.get("result") if isinstance(res, dict) else None
            if val:
                d = json.loads(val)
                d.setdefault("devices", {})
                return d
        except Exception:
            pass
        return {"devices": {}}

    def save(self, data):
        self._call("SET", DATA_KEY, json.dumps(data, ensure_ascii=False))


def get_store():
    if UPSTASH_URL and UPSTASH_TOKEN:
        return UpstashStore(UPSTASH_URL, UPSTASH_TOKEN)
    if os.environ.get("VERCEL"):
        return FileStore("/tmp/fuhx_devices.json")
    return FileStore(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "data", "devices.json"))


# ---------------------------------------------------------------- fingerprint
def _canon(v):
    if isinstance(v, dict):
        return "{" + ",".join(f"{k}:{_canon(v[k])}" for k in sorted(v)) + "}"
    if isinstance(v, (list, tuple)):
        return "[" + ",".join(_canon(x) for x in v) + "]"
    if v is None:
        return "null"
    return str(v)


def _h(*vals):
    return hashlib.sha256("|".join(str(v) for v in vals).encode()
                          ).hexdigest()[:16]


def components(fp):
    """10 high-entropy STABLE component — volatile field (battery/IP/usage)
    এখানে নেই, তাই session-to-session বদলায় না।"""
    ua = fp.get("uadata") or {}
    wg = fp.get("webgl") or {}
    scr = fp.get("screen") or {}
    mf = fp.get("mediaFeats") or {}
    pm = fp.get("perms") or {}
    intl = fp.get("intl") or {}
    return {
        # 1. canvas render hash (GPU+driver+OS dependent)
        "canvas": fp.get("canvas"),
        # 2. GPU identity + capability
        "webgl": _h(wg.get("vendor"), wg.get("renderer"), wg.get("maxTex"),
                    wg.get("extHash")),
        # 3. audio pipeline fingerprint
        "audio": fp.get("audio"),
        # 4. installed fonts set
        "fonts": fp.get("fonts"),
        # 5. TTS voice list (device/ROM dependent)
        "voices": fp.get("voices"),
        # 6. phone model + OS version (Client Hints)
        "model": _h(ua.get("platform"), ua.get("model"), ua.get("architecture"),
                    ua.get("platformVersion"), ua.get("brands")),
        # 7. screen hardware
        "screen": _h(scr.get("w"), scr.get("h"), scr.get("cd"),
                     scr.get("pr"), fp.get("orientation")),
        # 8. silicon
        "hw": _h(fp.get("cores"), fp.get("ram"), fp.get("touch"),
                 fp.get("memBucket")),
        # 9. locale identity
        "locale": _h(fp.get("lang"), fp.get("languages"), fp.get("tz"),
                     fp.get("tzOffset"), intl.get("calendar"),
                     intl.get("numberingSystem")),
        # 10. OS/browser environment quirks
        "env": _h(fp.get("platform"), mf.get("dark"), mf.get("coarse"),
                  mf.get("hover"), pm.get("camera"), pm.get("microphone"),
                  pm.get("notifications"), fp.get("pdfViewer"),
                  fp.get("webdriver")),
    }


def fingerprint_hash(fp):
    return hashlib.sha256(_canon(components(fp)).encode()).hexdigest()


def find_device(devices, fp):
    """(record, match_type, score). exact -> full hash; নাহলে fuzzy >= 8/10."""
    fph = fingerprint_hash(fp)
    if fph in devices:
        return devices[fph], "exact", 10
    comp = components(fp)
    best, best_score = None, 0
    for rec in devices.values():
        rc = rec.get("comp") or {}
        score = sum(1 for k, v in comp.items() if v and rc.get(k) == v)
        if score > best_score:
            best, best_score = rec, score
    if best is not None and best_score >= FUZZY_THRESHOLD:
        return best, "fuzzy", best_score
    return None, None, best_score


def device_summary(fp, ip, match=None, score=None):
    ua = fp.get("uadata") or {}
    wg = fp.get("webgl") or {}
    scr = fp.get("screen") or {}
    bat = fp.get("battery")
    sto = fp.get("storage")
    tg = fp.get("tg") or {}
    out = {
        "ip": ip,
        "platform": fp.get("platform"),
        "model": ua.get("model") or None,
        "ua": str(fp.get("ua") or "")[:90],
        "screen": f"{scr.get('w')}x{scr.get('h')}" if scr.get("w") else None,
        "cores": fp.get("cores"),
        "ram_gb": fp.get("ram"),
        "battery": (f"{bat.get('level')}%"
                    if isinstance(bat, dict) and bat.get("level") is not None
                    else None),
        "storage_quota_gb": (round(sto["quota"] / 1e9, 1)
                             if isinstance(sto, dict) and sto.get("quota")
                             else None),
        "tz": fp.get("tz"),
        "lang": fp.get("lang"),
        "gpu": str(wg.get("renderer") or "")[:60] or None,
        "match": match,
        "match_score": score,
    }
    if tg.get("tg_uid"):
        out["tg_webapp_uid"] = tg.get("tg_uid")
    return {k: v for k, v in out.items() if v is not None}


# ---------------------------------------------------------------- link signature (bot -> site)
def sign_link(uid, t):
    msg = f"{uid}.{t}".encode()
    return hmac.new(WEBHOOK_SECRET.encode(), msg, hashlib.sha256).hexdigest()


def verify_link_sig(uid, t, sig, now=None):
    """WEBHOOK_SECRET set না থাকলে dev-mode: signature skip."""
    if not WEBHOOK_SECRET:
        return True
    if not uid or not t or not sig:
        return False
    try:
        if abs(int(now or time.time()) - int(t)) > LINK_TTL:
            return False
    except (TypeError, ValueError):
        return False
    good = sign_link(str(uid), str(t))
    return hmac.compare_digest(good, str(sig))


# ---------------------------------------------------------------- webhook (site -> bot)
def send_webhook(payload):
    """Bot-এর webhook URL-এ signed JSON POST. (NagorikPay pattern-এর মতো)"""
    if not BOT_WEBHOOK_URL or not WEBHOOK_SECRET:
        return False, "webhook not configured (BOT_WEBHOOK_URL / WEBHOOK_SECRET)"
    body = json.dumps(payload, ensure_ascii=False).encode()
    sig = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    req = urllib.request.Request(
        BOT_WEBHOOK_URL, data=body,
        headers={"Content-Type": "application/json", "X-FUHX-Sig": sig})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return True, f"http {r.status}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


# ---------------------------------------------------------------- core logic (pure, testable)
# NOTE: Vercel CLI 57+ requires a SINGLE WSGI/ASGI entrypoint
# (pyproject.toml -> api.index:app). process_request() is the shared logic
# used by both the WSGI app (api/index.py) and the legacy handler below.
def process_request(payload, ip):
    uid = payload.get("uid")
    fp = payload.get("fp")
    if not uid or not isinstance(fp, dict):
        return 400, {"ok": False, "error": "uid and fp required"}
    if not verify_link_sig(str(uid), str(payload.get("t") or ""),
                           str(payload.get("sig") or "")):
        return 403, {"ok": False, "error": "bad or expired link signature"}
    try:
        result = process_verification(uid, fp, ip, get_store())
    except Exception:
        return 500, {"ok": False, "error": "server error"}
    result["ok"] = True
    return 200, result


def process_verification(uid, fp, ip, store, now=None):
    now = int(now or time.time())
    ts = utcnow_iso()
    uid = str(uid)
    data = store.load()
    devices = data.setdefault("devices", {})

    rec, match, score = find_device(devices, fp)
    comp = components(fp)
    fph = fingerprint_hash(fp)

    tg = fp.get("tg") or {}
    tg_uid = tg.get("tg_uid")
    tg_mismatch = bool(tg_uid and tg_uid != uid)

    hook_base = {"uid": uid, "fph": fph[:12], "ip": ip, "ts": ts,
                 "device": device_summary(fp, ip, match, score),
                 "match": match, "match_score": score,
                 "tg_webapp_uid": tg_uid, "tg_uid_mismatch": tg_mismatch}

    if rec is None:
        token = secrets.token_urlsafe(16)
        devices[fph] = {
            "uid": uid, "uids_seen": [uid], "strikes": 0, "token": token,
            "ip": ip, "device": device_summary(fp, ip, "new", 0),
            "comp": comp, "first_seen": ts, "last_seen": ts,
        }
        store.save(data)
        payload = dict(hook_base, status="success", kind="new",
                       strike=0, verify_token=token)
        ok, info = send_webhook(payload)
        return {"status": "success", "strike": 0, "kind": "new",
                "verify_token": token, "webhook_ok": ok, "webhook_info": info,
                "message": "Verification successful"}

    # device আগেই দেখা গেছে (exact বা fuzzy)
    rec["last_seen"] = ts
    rec["ip"] = ip
    rec["comp"] = comp  # latest stable components refresh
    if str(uid) not in rec.get("uids_seen", []):
        rec.setdefault("uids_seen", []).append(uid)

    if str(uid) == str(rec.get("uid")):
        store.save(data)
        payload = dict(hook_base, status="success", kind="again",
                       strike=0, verify_token=rec.get("token"))
        ok, info = send_webhook(payload)
        return {"status": "success", "strike": 0, "kind": "again",
                "verify_token": rec.get("token"), "webhook_ok": ok,
                "webhook_info": info,
                "message": "Already verified on this device"}

    # অন্য Telegram account, same device -> strike
    rec["strikes"] = int(rec.get("strikes", 0)) + 1
    store.save(data)
    strike = rec["strikes"]
    status = "blocked" if strike >= MAX_STRIKES else "rejected"
    payload = dict(hook_base, status=status, kind="duplicate",
                   strike=strike, max_strikes=MAX_STRIKES,
                   owner_uid=str(rec.get("uid")))
    ok, info = send_webhook(payload)
    return {"status": status, "strike": strike, "kind": "duplicate",
            "match": match, "match_score": score,
            "verify_token": None, "webhook_ok": ok, "webhook_info": info,
            "message": ("Device blocked after 3 warnings"
                        if status == "blocked"
                        else "This device is already verified with another account")}


# ---------------------------------------------------------------- HTTP handler (Vercel)
class handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _client_ip(self):
        fwd = self.headers.get("x-forwarded-for", "")
        if fwd:
            return fwd.split(",")[0].strip()
        return self.client_address[0] if self.client_address else "unknown"

    def do_GET(self):
        self._send(200, {"ok": True, "service": "FUHX IP Verify",
                         "usage": "POST fingerprint JSON to this endpoint"})

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            length = 0
        if length <= 0 or length > 300_000:
            self._send(400, {"ok": False, "error": "bad body"})
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            self._send(400, {"ok": False, "error": "invalid json"})
            return

        code, result = process_request(payload, self._client_ip())
        self._send(code, result)

    def log_message(self, *args):
        pass
