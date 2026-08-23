# Tuya Album Lights

Spicetify UI + a local Python service that sets a **Tuya / Wipro / Smart Life** RGB light to the colour of the album playing in desktop Spotify.

<img src="img/preview.png" alt="Album cover colour driving a smart bulb" width="420" />

**Repo:** [github.com/not-An-human/tuya-album-lights](https://github.com/not-An-human/tuya-album-lights)

## How it works

```
Desktop Spotify (album art)
  → bundled bridge.py (polls the player, reads the cover)
  → Tuya Cloud
  → your bulb

Spicetify popup / sidebar
  → saves Access ID, secret, device ID
```

The Spotify client cannot call Tuya’s API directly (CORS). The bridge runs on this PC. On Linux it follows Spotify with `playerctl`, so colours keep updating even if the in-app extension cannot reach localhost.

**On/off:** click the bulb in Spotify’s top bar, or **Album lights** in the profile menu. Off stops sync and turns the bulb off.

## What’s in this folder

| File | Purpose |
| --- | --- |
| `tuya-album-lights.js` | Spicetify extension (settings popup) |
| `app/` | Sidebar settings page + `bridge.py` |
| `install.py` | Installer for Windows, macOS, and Linux |
| `manifest.json` | Spicetify Marketplace listing |
| `LICENSE` | MIT |

---

## 1. Tuya cloud (once)

1. Create a free account at [iot.tuya.com](https://iot.tuya.com). This is **not** the phone app.
2. **Cloud → Development → Create project**
   - Development method: **Smart Home**
   - Data centre: same region as the phone app (India → **India** / `in`)
3. **Service API → Go to Authorize** and enable at least:
   - IoT Core
   - Authorization Token Management
   - Smart Home Basic Service
4. Put the bulb in the **Tuya Smart** or **Smart Life** app (Wipro’s own app is not enough for linking).
5. **Devices → Link Tuya App Account** → scan the QR. Refresh it if it expired. Top-right data centre must match the app **Region**.
6. Copy from **Overview**: Access ID and Access Secret.
7. Copy the light’s **Device ID** from **Devices**.

Phone app region: **Me → Settings → Account and Security → Region**.

---

## 2. Install

Need [Spicetify](https://spicetify.app/), [Python 3](https://www.python.org/) (with Pillow), and on Linux [playerctl](https://github.com/altdesktop/playerctl).

```bash
python3 install.py
```

Windows (if `python3` is not a command):

```bat
python install.py
```

That copies the extension, the sidebar app, and the bridge, then starts the bridge at login.

Restart Spotify. If keys are empty, a **popup** opens. You can also use **Tuya Lights** in the left sidebar.

| Field | Where it comes from |
| --- | --- |
| Access ID | iot.tuya.com → project Overview |
| Access Secret | same page |
| Data centre | `in` `eu` `eu-w` `us` `us-e` `sg` `cn` |
| Device ID | iot.tuya.com → Devices |
| Bridge URL | `http://127.0.0.1:18765` |

Keys are stored on this computer (`~/.config/tuya-album-lights/config.json` on Linux/macOS).

---

## 3. If the light never changes

- `http://127.0.0.1:18765/health` should include `"configured": true`
- Linux: `playerctl -p spotify status` should say `Playing`
- Linux: `journalctl --user -u tuya-album-lights-bridge -f` should log `sync Artist — Title`

Re-run `python3 install.py` if the bridge is not running.

The bulb must support RGB (`colour` / `colour_data_v2`), not white-only.

---

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| Bridge not running | `python3 install.py` |
| `"configured": false` | Save keys in the Spotify popup or sidebar |
| permission deny / 1106 | Authorize IoT Core; extend the free trial |
| QR / data centre error | App **Region** must match the cloud project |
| Linux: no colour changes | Install `playerctl`; keep desktop Spotify playing |

Marketplace → **Installed** only lists extensions installed from Marketplace. This project is tagged `spicetify-extensions` so it can show up there after GitHub indexes it.

## License

MIT
