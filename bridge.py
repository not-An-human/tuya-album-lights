#!/usr/bin/env python3
"""Local CORS bridge so a Spicetify extension can talk to Tuya Cloud.

Spotify's origin is not allowed by Tuya's API, so this tiny localhost
server signs and forwards colour commands.

Bind: 127.0.0.1:18765  (localhost only)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

HOST = "127.0.0.1"
PORT = 18765

REGIONS = {
    "cn": "openapi.tuyacn.com",
    "us": "openapi.tuyaus.com",
    "az": "openapi.tuyaus.com",
    "us-e": "openapi-ueaz.tuyaus.com",
    "ue": "openapi-ueaz.tuyaus.com",
    "eu": "openapi.tuyaeu.com",
    "eu-w": "openapi-weaz.tuyaeu.com",
    "we": "openapi-weaz.tuyaeu.com",
    "in": "openapi.tuyain.com",
    "sg": "openapi-sg.iotbing.com",
}

# Tiny in-memory token cache: (access_id, region) -> {token, host, expire_at}
_TOKEN = {}
TOKEN_REFRESH_SKEW = 120  # refresh 2 minutes before Tuya expiry


def _sha256_hex(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _sign(secret: str, payload: str) -> str:
    return hmac.new(
        secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest().upper()


def tuya_request(
    host: str,
    path: str,
    access_id: str,
    access_secret: str,
    token: str | None,
    method: str = "GET",
    body_obj=None,
) -> dict:
    url = f"https://{host}{path}"
    body = json.dumps(body_obj) if body_obj is not None else ""
    headers: dict[str, str] = {}
    if body_obj is not None:
        headers["Content-type"] = "application/json"
        headers["Signature-Headers"] = "Content-type"

    now = str(int(__import__("time").time() * 1000))
    payload = access_id + (token or "") + now
    payload += (
        f"{method}\n"
        f"{_sha256_hex(body)}\n"
        + "".join(
            f"{key}:{headers[key]}\n"
            for key in headers.get("Signature-Headers", "").split(":")
            if key in headers
        )
        + "\n"
        + path
    )

    send_headers = {
        **headers,
        "client_id": access_id,
        "sign": _sign(access_secret, payload),
        "t": now,
        "sign_method": "HMAC-SHA256",
        "mode": "cors",
    }
    if token:
        send_headers["access_token"] = token

    req = Request(url, data=body.encode("utf-8") if body else None, method=method)
    for k, v in send_headers.items():
        req.add_header(k, v)

    try:
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as err:
        raw = err.read().decode(errors="replace")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"success": False, "msg": raw or str(err)}
    except URLError as err:
        return {"success": False, "msg": str(err.reason or err)}


def get_token(access_id: str, access_secret: str, region: str) -> tuple[str, str]:
    cache_key = f"{access_id}:{region}"
    cached = _TOKEN.get(cache_key)
    now = __import__("time").time()
    if cached and now < cached.get("expire_at", 0):
        return cached["token"], cached["host"]

    host = REGIONS.get(region.lower(), REGIONS["in"])
    data = tuya_request(
        host,
        "/v1.0/token?grant_type=1",
        access_id,
        access_secret,
        token=None,
        method="GET",
    )
    if not data.get("success"):
        _TOKEN.pop(cache_key, None)
        raise RuntimeError(data.get("msg") or json.dumps(data))
    result = data["result"]
    token = result["access_token"]
    ttl = int(result.get("expire_time") or 7200)
    _TOKEN[cache_key] = {
        "token": token,
        "host": host,
        "expire_at": now + max(ttl - TOKEN_REFRESH_SKEW, 30),
    }
    return token, host


def set_colour(payload: dict) -> dict:
    access_id = payload["accessId"].strip()
    access_secret = payload["accessSecret"].strip()
    region = (payload.get("region") or "in").strip().lower()
    device_id = payload["deviceId"].strip()
    hsv = payload["hsv"]

    token, host = get_token(access_id, access_secret, region)
    body = {
        "commands": [
            {"code": "switch_led", "value": True},
            {"code": "work_mode", "value": "colour"},
            {
                "code": "colour_data_v2",
                "value": {
                    "h": int(hsv["h"]) % 360,
                    "s": int(hsv["s"]),
                    "v": int(hsv["v"]),
                },
            },
        ]
    }
    path = f"/v1.0/iot-03/devices/{device_id}/commands"
    data = tuya_request(
        host, path, access_id, access_secret, token, method="POST", body_obj=body
    )
    if not data.get("success"):
        msg = str(data.get("msg") or "").lower()
        code = data.get("code")
        if code in (1004, 1010, 1011) or "token" in msg:
            _TOKEN.pop(f"{access_id}:{region}", None)
            token, host = get_token(access_id, access_secret, region)
            data = tuya_request(
                host, path, access_id, access_secret, token, method="POST", body_obj=body
            )
    return data


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write("[bridge] " + (fmt % args) + "\n")

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path in ("/", "/health"):
            self._json(200, {"ok": True, "service": "tuya-album-lights-bridge"})
            return
        self._json(404, {"ok": False, "msg": "not found"})

    def do_POST(self):
        if self.path not in ("/color", "/v1/color"):
            self._json(404, {"ok": False, "msg": "not found"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length).decode())
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._json(400, {"ok": False, "msg": "invalid json"})
            return
        required = ("accessId", "accessSecret", "deviceId", "hsv")
        missing = [k for k in required if k not in payload]
        if missing:
            self._json(400, {"ok": False, "msg": f"missing {missing}"})
            return
        try:
            result = set_colour(payload)
        except Exception as exc:  # noqa: BLE001
            self._json(502, {"ok": False, "msg": str(exc)})
            return
        if not result.get("success"):
            self._json(502, {"ok": False, "tuya": result})
            return
        self._json(200, {"ok": True, "tuya": result})

    def _json(self, status: int, obj: dict):
        raw = json.dumps(obj).encode()
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def main():
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"tuya-album-lights bridge on http://{HOST}:{PORT}")
    print("Keep this running while Spotify is open. Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
