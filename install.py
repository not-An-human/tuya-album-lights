#!/usr/bin/env python3
"""Install Tuya Album Lights on Windows, macOS, and Linux."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PYTHON = sys.executable


def spicetify_config_dir() -> Path:
    try:
        cfg = subprocess.check_output(["spicetify", "-c"], text=True).strip()
        if cfg:
            return Path(cfg).expanduser().parent
    except (OSError, subprocess.CalledProcessError):
        pass
    if os.name == "nt":
        return Path.home() / ".spicetify"
    return Path.home() / ".config" / "spicetify"


def run_spicetify(*args: str) -> None:
    subprocess.check_call(["spicetify", *args])


def copy_files(dest_app: Path, dest_ext: Path) -> Path:
    dest_app.mkdir(parents=True, exist_ok=True)
    dest_ext.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "tuya-album-lights.js", dest_ext / "tuya-album-lights.js")
    for name in ("index.js", "style.css", "manifest.json", "bridge.py"):
        shutil.copy2(ROOT / "app" / name, dest_app / name)
    bridge = dest_app / "bridge.py"
    try:
        bridge.chmod(bridge.stat().st_mode | 0o111)
    except OSError:
        pass
    return bridge


def install_autostart(bridge: Path) -> str:
    if sys.platform == "win32":
        startup = (
            Path(os.environ["APPDATA"])
            / "Microsoft"
            / "Windows"
            / "Start Menu"
            / "Programs"
            / "Startup"
        )
        startup.mkdir(parents=True, exist_ok=True)
        bat = startup / "tuya-album-lights-bridge.bat"
        pyw = Path(PYTHON).with_name("pythonw.exe")
        runner = pyw if pyw.exists() else Path(PYTHON)
        bat.write_text(
            f'@echo off\nstart "" "{runner}" "{bridge}"\n',
            encoding="utf-8",
        )
        return str(bat)

    if sys.platform == "darwin":
        agents = Path.home() / "Library" / "LaunchAgents"
        agents.mkdir(parents=True, exist_ok=True)
        plist_path = agents / "com.tuya-album-lights.bridge.plist"
        plist_path.write_text(
            f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.tuya-album-lights.bridge</string>
  <key>ProgramArguments</key>
  <array>
    <string>{PYTHON}</string>
    <string>{bridge}</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
</dict>
</plist>
""",
            encoding="utf-8",
        )
        subprocess.call(["launchctl", "unload", str(plist_path)])
        subprocess.check_call(["launchctl", "load", str(plist_path)])
        return str(plist_path)

    unit_dir = Path.home() / ".config" / "systemd" / "user"
    if shutil.which("systemctl"):
        unit_dir.mkdir(parents=True, exist_ok=True)
        unit = unit_dir / "tuya-album-lights-bridge.service"
        unit.write_text(
            f"""[Unit]
Description=Tuya Album Lights local bridge
After=network.target

[Service]
ExecStart={PYTHON} {bridge}
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
""",
            encoding="utf-8",
        )
        subprocess.call(["systemctl", "--user", "daemon-reload"])
        subprocess.check_call(
            ["systemctl", "--user", "enable", "--now", "tuya-album-lights-bridge.service"]
        )
        return str(unit)

    auto = Path.home() / ".config" / "autostart"
    auto.mkdir(parents=True, exist_ok=True)
    desktop = auto / "tuya-album-lights-bridge.desktop"
    desktop.write_text(
        f"""[Desktop Entry]
Type=Application
Name=Tuya Album Lights Bridge
Exec={PYTHON} {bridge}
Terminal=false
X-GNOME-Autostart-enabled=true
""",
        encoding="utf-8",
    )
    return str(desktop)


def start_bridge_now(bridge: Path) -> None:
    if sys.platform == "win32":
        subprocess.Popen(
            [PYTHON, str(bridge)],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return
    if sys.platform == "darwin":
        return
    if shutil.which("systemctl"):
        return
    subprocess.Popen([PYTHON, str(bridge)], start_new_session=True)


def ensure_pillow() -> None:
    try:
        import PIL  # noqa: F401
    except ImportError:
        print("Installing Pillow…")
        subprocess.check_call([PYTHON, "-m", "pip", "install", "--user", "Pillow"])


def main() -> None:
    spic = spicetify_config_dir()
    app_dir = spic / "CustomApps" / "tuya-album-lights"
    ext_dir = spic / "Extensions"
    print(f"Spicetify folder: {spic}")
    ensure_pillow()
    if sys.platform.startswith("linux") and not shutil.which("playerctl"):
        print("Note: install playerctl so the bridge can follow desktop Spotify.")
    bridge = copy_files(app_dir, ext_dir)
    run_spicetify("config", "extensions", "tuya-album-lights.js")
    run_spicetify("config", "custom_apps", "tuya-album-lights")
    autostart = install_autostart(bridge)
    start_bridge_now(bridge)
    run_spicetify("apply")
    print()
    print("Installed on this OS.")
    print(f"  App + bundled bridge: {app_dir}")
    print(f"  Auto-start:           {autostart}")
    print("Restart Spotify and paste your Tuya keys in the popup (or sidebar Tuya Lights).")


if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError as err:
        sys.exit(f"Need Spicetify and Python 3 on PATH. Missing: {err}")
    except subprocess.CalledProcessError as err:
        sys.exit(f"Command failed: {err}")
