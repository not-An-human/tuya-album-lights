const react = Spicetify.React;
const { useState } = react;

const STORAGE_KEY = "tuya-album-lights-settings";
const DEFAULTS = {
  enabled: true,
  accessId: "",
  accessSecret: "",
  region: "in",
  deviceId: "",
  bridgeUrl: "http://127.0.0.1:18765",
};

function loadSettings() {
  try {
    return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}") };
  } catch {
    return { ...DEFAULTS };
  }
}

function Field({ label, children }) {
  return react.createElement(
    "div",
    { style: { display: "flex", flexDirection: "column", gap: "6px" } },
    react.createElement("label", null, label),
    children
  );
}

function Page() {
  const initial = loadSettings();
  const [enabled, setEnabled] = useState(initial.enabled);
  const [accessId, setAccessId] = useState(initial.accessId);
  const [accessSecret, setAccessSecret] = useState(initial.accessSecret);
  const [region, setRegion] = useState(initial.region);
  const [deviceId, setDeviceId] = useState(initial.deviceId);
  const [bridgeUrl, setBridgeUrl] = useState(initial.bridgeUrl);

  const onSave = () => {
    const payload = {
      enabled,
      accessId: accessId.trim(),
      accessSecret: accessSecret.trim(),
      region,
      deviceId: deviceId.trim(),
      bridgeUrl: bridgeUrl.trim() || DEFAULTS.bridgeUrl,
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
    fetch(`${payload.bridgeUrl.replace(/\/$/, "")}/settings`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).catch(() => {});
    Spicetify.showNotification("Tuya keys saved — skip a track to sync");
  };

  return react.createElement(
    "div",
    { className: "tal-page" },
    react.createElement("h1", null, "Tuya Album Lights"),
    react.createElement(
      "p",
      { className: "lead" },
      "Paste your Tuya IoT Access ID, secret, and device ID. The Python bridge is bundled and auto-starts — you only fill this form."
    ),
    react.createElement(
      "form",
      {
        className: "tal-form",
        onSubmit: (e) => {
          e.preventDefault();
          onSave();
        },
      },
      react.createElement(
        "label",
        { className: "tal-check" },
        react.createElement("input", {
          type: "checkbox",
          checked: enabled,
          onChange: (e) => setEnabled(e.target.checked),
        }),
        " Enable album colour sync"
      ),
      react.createElement(Field, { label: "Access ID / Client ID" },
        react.createElement("input", {
          value: accessId,
          onChange: (e) => setAccessId(e.target.value),
          autoComplete: "off",
        })
      ),
      react.createElement(Field, { label: "Access Secret / Client Secret" },
        react.createElement("input", {
          type: "password",
          value: accessSecret,
          onChange: (e) => setAccessSecret(e.target.value),
          autoComplete: "off",
        })
      ),
      react.createElement(Field, { label: "Data centre" },
        react.createElement(
          "select",
          { value: region, onChange: (e) => setRegion(e.target.value) },
          ["in", "eu", "eu-w", "us", "us-e", "sg", "cn"].map((r) =>
            react.createElement("option", { key: r, value: r }, r)
          )
        )
      ),
      react.createElement(Field, { label: "Device ID" },
        react.createElement("input", {
          value: deviceId,
          onChange: (e) => setDeviceId(e.target.value),
          placeholder: "from iot.tuya.com → Devices",
        })
      ),
      react.createElement(Field, { label: "Local bridge URL" },
        react.createElement("input", {
          value: bridgeUrl,
          onChange: (e) => setBridgeUrl(e.target.value),
        })
      ),
      react.createElement("button", { className: "tal-save", type: "submit" }, "Save")
    )
  );
}

function render() {
  return react.createElement(Page, null);
}
