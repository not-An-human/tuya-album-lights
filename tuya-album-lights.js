// NAME: Tuya Album Lights
// AUTHOR: aliimww
// DESCRIPTION: Sync Tuya / Wipro / Smart Life lights to the current album cover colour.

(function TuyaAlbumLights() {
  const STORAGE_KEY = "tuya-album-lights-settings";
  const DEFAULTS = {
    enabled: true,
    accessId: "",
    accessSecret: "",
    region: "in",
    deviceId: "",
    bridgeUrl: "http://127.0.0.1:18765",
  };

  let lastArt = "";
  let lastHsvKey = "";
  let pending = false;

  function waitForSpicetify() {
    if (!window.Spicetify || !Spicetify.Player || !Spicetify.Menu) {
      setTimeout(waitForSpicetify, 300);
      return;
    }
    init();
  }

  function getSettings() {
    try {
      return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}") };
    } catch {
      return { ...DEFAULTS };
    }
  }

  function saveSettings(settings) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
  }

  function rgbToTuyaHsv(r, g, b) {
    r /= 255;
    g /= 255;
    b /= 255;
    const max = Math.max(r, g, b);
    const min = Math.min(r, g, b);
    const d = max - min;
    let h = 0;
    if (d !== 0) {
      switch (max) {
        case r:
          h = ((g - b) / d + (g < b ? 6 : 0)) / 6;
          break;
        case g:
          h = ((b - r) / d + 2) / 6;
          break;
        default:
          h = ((r - g) / d + 4) / 6;
      }
    }
    let s = max === 0 ? 0 : d / max;
    let v = max;
    s = Math.max(s, 0.55);
    v = Math.max(v, 0.75);
    return {
      h: Math.round(h * 360) % 360,
      s: Math.round(s * 1000),
      v: Math.round(v * 1000),
    };
  }

  function pickRgb(colors) {
    if (!colors || !colors.length) return null;
    const raw = colors[0]?.colorRaw?.rgb || colors[0]?.colorRaw;
    if (raw && typeof raw.r === "number") return raw;
    return null;
  }

  async function sendColour(settings, hsv) {
    const url = `${settings.bridgeUrl.replace(/\/$/, "")}/color`;
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        accessId: settings.accessId,
        accessSecret: settings.accessSecret,
        region: settings.region,
        deviceId: settings.deviceId,
        hsv,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.ok === false) {
      const msg = data.msg || data.tuya?.msg || `HTTP ${res.status}`;
      throw new Error(msg);
    }
  }

  async function handleSongChange() {
    const settings = getSettings();
    if (!settings.enabled) return;
    if (!settings.accessId || !settings.accessSecret || !settings.deviceId) {
      return;
    }

    const item = Spicetify.Player.data?.item;
    if (!item) return;

    const art =
      item.metadata?.image_xlarge_url ||
      item.metadata?.image_large_url ||
      item.metadata?.image_url ||
      item.album?.images?.[0]?.url ||
      "";

    if (!art || art === lastArt || pending) return;
    pending = true;

    try {
      let hsv;
      if (Spicetify.extractColorPreset) {
        const colors = await Spicetify.extractColorPreset(art);
        const rgb = pickRgb(colors);
        if (!rgb) {
          pending = false;
          return;
        }
        hsv = rgbToTuyaHsv(rgb.r, rgb.g, rgb.b);
      } else {
        pending = false;
        return;
      }

      const key = `${hsv.h}:${hsv.s}:${hsv.v}`;
      if (key === lastHsvKey) {
        lastArt = art;
        pending = false;
        return;
      }

      await sendColour(settings, hsv);
      lastArt = art;
      lastHsvKey = key;
      console.debug("[tuya-album-lights]", item.name, hsv);
    } catch (err) {
      console.error("[tuya-album-lights]", err);
      const message = String(err.message || err);
      if (message.includes("Failed to fetch") || message.includes("NetworkError")) {
        Spicetify.showNotification(
          "Tuya Album Lights: start the bundled bridge (python install.py)",
          true,
          4000
        );
      } else {
        Spicetify.showNotification(`Tuya Album Lights: ${message}`, true, 4000);
      }
    } finally {
      pending = false;
    }
  }

  function field(label, id, type, value, extra = "") {
    const safe = String(value)
      .replace(/&/g, "&amp;")
      .replace(/"/g, "&quot;")
      .replace(/</g, "&lt;");
    return `
      <label class="tal-label" for="${id}">${label}</label>
      <input class="tal-input" id="${id}" type="${type}" value="${safe}" ${extra} />
    `;
  }

  function openSettings() {
    const s = getSettings();
    const content = document.createElement("div");
    content.innerHTML = `
      <style>
        .tal-wrap { display:flex; flex-direction:column; gap:10px; min-width:360px; padding-bottom:8px; }
        .tal-label { font-size:12px; font-weight:700; opacity:.8; }
        .tal-input, .tal-select {
          background: var(--spice-main-alt, #282828);
          color: var(--spice-text, #fff);
          border: 1px solid var(--spice-button-disabled, #535353);
          border-radius: 8px; padding: 10px 12px; font-size: 14px;
        }
        .tal-row { display:flex; align-items:center; gap:10px; }
        .tal-help { font-size:12px; opacity:.7; line-height:1.4; }
        .tal-save {
          margin-top: 8px; background: var(--spice-button, #1db954); color:#000;
          border:none; border-radius:999px; padding:10px 16px; font-weight:700; cursor:pointer;
        }
      </style>
      <div class="tal-wrap">
        <div class="tal-row">
          <input id="tal-enabled" type="checkbox" ${s.enabled ? "checked" : ""} />
          <label for="tal-enabled">Enable album colour sync</label>
        </div>
        ${field("Tuya Access ID / Client ID", "tal-accessId", "text", s.accessId)}
        ${field("Tuya Access Secret / Client Secret", "tal-accessSecret", "password", s.accessSecret)}
        <label class="tal-label" for="tal-region">Data centre</label>
        <select class="tal-select" id="tal-region">
          ${["in", "eu", "eu-w", "us", "us-e", "sg", "cn"]
            .map(
              (r) =>
                `<option value="${r}" ${s.region === r ? "selected" : ""}>${r}</option>`
            )
            .join("")}
        </select>
        ${field("Device ID", "tal-deviceId", "text", s.deviceId, 'placeholder="from Tuya IoT → Devices"')}
        ${field("Local bridge URL", "tal-bridgeUrl", "text", s.bridgeUrl)}
        <p class="tal-help">
          The Python bridge is bundled with the app and should auto-start.
        </p>
        <button class="tal-save" id="tal-save" type="button">Save</button>
      </div>
    `;

    Spicetify.PopupModal.display({
      title: "Tuya Album Lights",
      content,
      isLarge: true,
    });

    content.querySelector("#tal-save").addEventListener("click", () => {
      const next = {
        enabled: content.querySelector("#tal-enabled").checked,
        accessId: content.querySelector("#tal-accessId").value.trim(),
        accessSecret: content.querySelector("#tal-accessSecret").value.trim(),
        region: content.querySelector("#tal-region").value,
        deviceId: content.querySelector("#tal-deviceId").value.trim(),
        bridgeUrl: content.querySelector("#tal-bridgeUrl").value.trim() || DEFAULTS.bridgeUrl,
      };
      saveSettings(next);
      lastArt = "";
      lastHsvKey = "";
      Spicetify.PopupModal.hide();
      Spicetify.showNotification("Tuya Album Lights settings saved");
      handleSongChange();
    });
  }

  function init() {
    Spicetify.Player.addEventListener("songchange", handleSongChange);
    Spicetify.Player.addEventListener("onplaypause", (event) => {
      if (event?.data && !event.data.isPaused) handleSongChange();
    });
    setInterval(() => {
      const art =
        Spicetify.Player.data?.item?.metadata?.image_url ||
        Spicetify.Player.data?.item?.album?.images?.[0]?.url ||
        "";
      if (art && art !== lastArt) handleSongChange();
    }, 2000);

    const bulbIcon =
      `<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M9 21c0 .55.45 1 1 1h4c.55 0 1-.45 1-1v-1H9v1zm3-19C8.14 2 5 5.14 5 9c0 2.38 1.19 4.47 3 5.74V17c0 .55.45 1 1 1h6c.55 0 1-.45 1-1v-2.26c1.81-1.27 3-3.36 3-5.74 0-3.86-3.14-7-7-7z"/></svg>`;

    new Spicetify.Menu.Item("Tuya Album Lights", false, openSettings, bulbIcon).register();

    if (Spicetify.Topbar?.Button) {
      new Spicetify.Topbar.Button("Tuya Lights", bulbIcon, openSettings, false);
    }

    const settings = getSettings();
    if (settings.enabled && settings.accessId && settings.deviceId) {
      setTimeout(handleSongChange, 1500);
    } else {
      setTimeout(openSettings, 1800);
    }
  }

  waitForSpicetify();
})();
