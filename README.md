# Tuya Album Lights

Spicetify extension that sets a **Tuya / Wipro / Smart Life** RGB light to the colour of the album you are playing in Spotify.

<img src="img/preview.png" alt="Album cover colour driving a smart bulb" width="420" />

Works on **Windows, macOS, and Linux**. Keys go in a **popup** when Spotify starts (if they are empty). You can also open **Tuya Lights** in the left sidebar, the top-bar bulb button, or the profile menu.

## How it works

```
Spotify (Spicetify)
  → album art colour
  → extension
  → http://127.0.0.1:18765
  → bundled bridge.py
  → your bulb
```

The JS extension is the same on every OS. A small Python bridge has to run on the same PC because Tuya’s API will not accept requests from Spotify itself. `install.py` copies that bridge next to the app and starts it at login on Windows (Startup folder), macOS (LaunchAgent), and Linux (systemd user or desktop autostart).

## What’s in this folder

| File | Purpose |
| --- | --- |
| `tuya-album-lights.js` | Spicetify extension (popup + colour sync) |
| `app/` | Sidebar settings page + bundled `bridge.py` |
| `install.py` | One installer for Windows / macOS / Linux |
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
4. **Devices → Link Tuya App Account** → scan the QR with **Smart Life** (or the OEM app the bulb is in). Refresh the QR if it expired. Top-right data centre must match the app **Region**.
5. Copy from **Overview**:
   - Access ID / Client ID
   - Access Secret / Client Secret
6. Copy the light’s **Device ID** from **Devices**.

Phone app region: **Me → Settings → Account and Security → Region**.

---

## 2. Install

Need [Spicetify](https://spicetify.app/) and [Python 3](https://www.python.org/) on your PATH.

```bash
python3 install.py
```

Windows (if `python3` is not a command):

```bat
python install.py
```

That copies the extension, the sidebar app, and `bridge.py`, then sets the bridge to start in the background.

Restart Spotify. If keys are empty, a **popup** opens.

Marketplace → **Installed** only shows extensions installed from Marketplace after this project is a public GitHub repo with topic `spicetify-extensions`.

---

## 3. If the light never changes

Open `http://127.0.0.1:18765/health` in a browser. You should see `{"ok": true}`.

If not, run the bundled bridge:

```bash
python3 install.py
```

Or start `app/bridge.py` with Python.

---

## 4. Put keys in Spotify

1. Open Spotify.
2. Use the popup, or **Tuya Lights** in the sidebar.
3. Fill in:

| Field | Example / notes |
| --- | --- |
| Enable | on |
| Access ID | from Tuya project Overview |
| Access Secret | from Tuya project Overview |
| Data centre | `in` `eu` `eu-w` `us` `us-e` `sg` `cn` |
| Device ID | from Tuya Devices list |
| Bridge URL | `http://127.0.0.1:18765` |

4. Save, play a song, skip once.

---

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| Notification about starting the bridge | Run `python install.py` (or `python3 install.py`) |
| permission deny / 1106 | Authorize IoT Core; extend the free trial on iot.tuya.com |
| QR / data centre error | App **Region** must match project data centre; refresh QR |
| Light does not change colour | Device must support RGB (`colour` / `colour_data_v2`) |
| Menu item missing | `spicetify config` should list `tuya-album-lights.js`; then `spicetify apply` |

---

## Publish this to GitHub (you)

1. Create an **empty** repo on GitHub (no README if you are uploading this folder as-is).
2. Drag everything in **this folder** into the repo.
3. Suggested topics: `spicetify-extensions`, `tuya`, `spotify`
4. Optional Marketplace: [Publishing to Marketplace](https://github.com/spicetify/marketplace/wiki/Publishing-to-Marketplace)

After the repo exists, edit `manifest.json` `authors[0].url` to your GitHub profile.

## License

MIT
