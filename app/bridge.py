#!/usr/bin/env python3
"""Local Tuya bridge + Spotify album-colour sync.

Listens on 127.0.0.1:18765 for the Spicetify UI, and also polls the
desktop Spotify player directly (playerctl) so sync keeps working even
when the Spotify client cannot call localhost.
"""

from __future__ import annotations

import colorsys
import hashlib
import hmac
import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

HOST = "127.0.0.1"
PORT = 18765
POLL_SECONDS = 2.0

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

_TOKEN = {}
TOKEN_REFRESH_SKEW = 120
_CONFIG_LOCK = threading.Lock()
_CONFIG: dict = {}


def config_path() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA") or Path.home())
        return base / "tuya-album-lights" / "config.json"
    return Path.home() / ".config" / "tuya-album-lights" / "config.json"


def load_config() -> dict:
    global _CONFIG
    path = config_path()
    if path.is_file():
        try:
            _CONFIG = json.loads(path.read_text())
        except json.JSONDecodeError:
            _CONFIG = {}
    return _CONFIG


def save_config(data: dict) -> None:
    global _CONFIG
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    merged = {**_CONFIG, **data}
    path.write_text(json.dumps(merged, indent=2) + "\n")
    _CONFIG = merged


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

    now = str(int(time.time() * 1000))
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
    now = time.time()
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


def send_commands(cfg: dict, commands: list) -> dict:
    access_id = cfg["accessId"].strip()
    access_secret = cfg["accessSecret"].strip()
    region = (cfg.get("region") or "in").strip().lower()
    device_id = cfg["deviceId"].strip()
    token, host = get_token(access_id, access_secret, region)
    path = f"/v1.0/iot-03/devices/{device_id}/commands"
    data = tuya_request(
        host,
        path,
        access_id,
        access_secret,
        token,
        method="POST",
        body_obj={"commands": commands},
    )
    if not data.get("success"):
        msg = str(data.get("msg") or "").lower()
        if data.get("code") in (1004, 1010, 1011) or "token" in msg:
            _TOKEN.pop(f"{access_id}:{region}", None)
            token, host = get_token(access_id, access_secret, region)
            data = tuya_request(
                host,
                path,
                access_id,
                access_secret,
                token,
                method="POST",
                body_obj={"commands": commands},
            )
    return data


def set_power(on: bool) -> dict:
    with _CONFIG_LOCK:
        cfg = dict(_CONFIG)
    if not all(cfg.get(k) for k in ("accessId", "accessSecret", "deviceId")):
        return {"success": False, "msg": "not configured"}
    return send_commands(cfg, [{"code": "switch_led", "value": bool(on)}])


_RESET_ART = threading.Event()


def rgb_to_tuya_hsv(r: int, g: int, b: int) -> dict:
    h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    s = max(s, 0.55)
    v = max(v, 0.75)
    return {
        "h": int(round(h * 360)) % 360,
        "s": int(round(s * 1000)),
        "v": int(round(v * 1000)),
    }


def dominant_rgb(image_bytes: bytes) -> tuple[int, int, int] | None:
    from PIL import Image

    im = Image.open(BytesIO(image_bytes)).convert("RGB")
    im.thumbnail((64, 64))
    best = None
    best_score = -1.0
    pixels = list(getattr(im, "get_flattened_data", im.getdata)())
    step = max(1, len(pixels) // 400)
    for r, g, b in pixels[::step]:
        mx, mn = max(r, g, b), min(r, g, b)
        if mx < 40:
            continue
        sat = (mx - mn) / mx if mx else 0
        score = sat * 2 + (r + g + b) / (255 * 3)
        if score > best_score:
            best_score = score
            best = (r, g, b)
    return best


def playerctl(*args: str) -> str:
    for prefix in (["playerctl", "-p", "spotify"], ["playerctl"]):
        try:
            return subprocess.check_output(
                [*prefix, *args],
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=3,
            ).strip()
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            continue
    return ""


def fetch_bytes(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": "tuya-album-lights"})
    with urlopen(req, timeout=10) as resp:
        return resp.read()


def poll_spotify() -> None:
    last_art = ""
    log("spotify poller started")
    while True:
        try:
            if _RESET_ART.is_set():
                last_art = ""
                _RESET_ART.clear()
            with _CONFIG_LOCK:
                cfg = dict(_CONFIG)
            if cfg.get("enabled", True) is False:
                time.sleep(POLL_SECONDS)
                continue
            if not all(cfg.get(k) for k in ("accessId", "accessSecret", "deviceId")):
                time.sleep(POLL_SECONDS)
                continue
            if playerctl("status") != "Playing":
                time.sleep(POLL_SECONDS)
                continue
            art = playerctl("metadata", "mpris:artUrl")
            title = playerctl("metadata", "xesam:title")
            artist = playerctl("metadata", "xesam:artist")
            if not art or art == last_art:
                time.sleep(POLL_SECONDS)
                continue
            rgb = dominant_rgb(fetch_bytes(art))
            if not rgb:
                last_art = art
                time.sleep(POLL_SECONDS)
                continue
            hsv = rgb_to_tuya_hsv(*rgb)
            result = set_colour(
                {
                    "accessId": cfg["accessId"],
                    "accessSecret": cfg["accessSecret"],
                    "region": cfg.get("region") or "in",
                    "deviceId": cfg["deviceId"],
                    "hsv": hsv,
                }
            )
            if result.get("success"):
                last_art = art
                log(f"sync {artist} — {title} RGB{rgb} HSV{hsv}")
            else:
                log(f"tuya error: {result}")
        except Exception as exc:  # noqa: BLE001
            log(f"poller error: {exc}")
        time.sleep(POLL_SECONDS)


def log(msg: str) -> None:
    sys.stderr.write("[bridge] " + msg + "\n")
    sys.stderr.flush()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        log(fmt % args)

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Access-Control-Max-Age", "86400")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path in ("/", "/health"):
            with _CONFIG_LOCK:
                ready = bool(
                    _CONFIG.get("accessId")
                    and _CONFIG.get("accessSecret")
                    and _CONFIG.get("deviceId")
                )
            self._json(
                200,
                {
                    "ok": True,
                    "service": "tuya-album-lights-bridge",
                    "configured": ready,
                    "enabled": _CONFIG.get("enabled", True),
                },
            )
            return
        self._json(404, {"ok": False, "msg": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length).decode() or "{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._json(400, {"ok": False, "msg": "invalid json"})
            return

        if self.path in ("/settings", "/v1/settings", "/power", "/v1/power"):
            needed = {
                k: payload[k]
                for k in ("accessId", "accessSecret", "region", "deviceId", "enabled")
                if k in payload
            }
            if "on" in payload and "enabled" not in needed:
                needed["enabled"] = bool(payload["on"])
            with _CONFIG_LOCK:
                save_config(needed)
                enabled = _CONFIG.get("enabled", True)
            _RESET_ART.set()
            power = None
            try:
                power = set_power(bool(enabled))
            except Exception as exc:  # noqa: BLE001
                log(f"power error: {exc}")
            self._json(
                200,
                {"ok": True, "enabled": bool(enabled), "light": power},
            )
            return

        if self.path not in ("/color", "/v1/color"):
            self._json(404, {"ok": False, "msg": "not found"})
            return
        required = ("accessId", "accessSecret", "deviceId", "hsv")
        missing = [k for k in required if k not in payload]
        if missing:
            self._json(400, {"ok": False, "msg": f"missing {missing}"})
            return
        with _CONFIG_LOCK:
            save_config(
                {
                    "accessId": payload["accessId"],
                    "accessSecret": payload["accessSecret"],
                    "region": payload.get("region") or "in",
                    "deviceId": payload["deviceId"],
                    "enabled": True,
                }
            )
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
    load_config()
    threading.Thread(target=poll_spotify, name="spotify-poller", daemon=True).start()
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    log(f"listening on http://{HOST}:{PORT}")
    log(f"config {config_path()}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
