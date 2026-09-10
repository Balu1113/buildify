import React, { useRef } from "react";

const TINT_COLORS = [
  { name: "Transparent", color: "rgba(255,255,255,0.5)", hue: "0", glow: "rgba(255,255,255,0.05)" },
  { name: "White", color: "#ffffff", hue: "0", glow: "rgba(255,255,255,0.12)" },
  { name: "Light Blue", color: "#93c5fd", hue: "210", glow: "rgba(147,197,253,0.15)" },
  { name: "Lavender", color: "#c8b4ff", hue: "260", glow: "rgba(200,180,255,0.15)" },
  { name: "Blue", color: "#60a5fa", hue: "215", glow: "rgba(96,165,250,0.15)" },
  { name: "Cyan", color: "#67e8f9", hue: "180", glow: "rgba(103,232,249,0.15)" },
  { name: "Teal", color: "#5eead4", hue: "165", glow: "rgba(94,234,212,0.15)" },
  { name: "Green", color: "#86efac", hue: "140", glow: "rgba(134,239,172,0.15)" },
  { name: "Yellow", color: "#fde68a", hue: "48", glow: "rgba(253,230,138,0.15)" },
  { name: "Orange", color: "#fdba74", hue: "28", glow: "rgba(253,186,116,0.15)" },
  { name: "Pink", color: "#f9a8d4", hue: "325", glow: "rgba(249,168,212,0.15)" },
  { name: "Rose", color: "#fb7185", hue: "340", glow: "rgba(251,113,133,0.15)" },
];

const BG_COLORS = [
  { name: "Default", color: null },
  { name: "Charcoal", color: "#1a1a2e" },
  { name: "Navy", color: "#0f1b2d" },
  { name: "Deep Purple", color: "#160a2e" },
  { name: "Midnight Blue", color: "#0a1929" },
  { name: "Slate", color: "#1e293b" },
  { name: "Obsidian", color: "#0d0d0d" },
  { name: "Warm Gray", color: "#1c1917" },
  { name: "Dark Teal", color: "#0a1f1c" },
  { name: "Rich Black", color: "#050510" },
  { name: "Espresso", color: "#1a0f0a" },
  { name: "Storm", color: "#151820" },
  { name: "Snow", color: "#f8fafc" },
  { name: "Ivory", color: "#fefdf5" },
  { name: "Linen", color: "#faf5ef" },
  { name: "Pearl", color: "#f0eef6" },
  { name: "Mist", color: "#eef2f7" },
  { name: "Cloud", color: "#f1f5f9" },
  { name: "Lavender Mist", color: "#f3f0ff" },
  { name: "Rose Quartz", color: "#fdf2f4" },
  { name: "Seafoam", color: "#f0fdf9" },
  { name: "Peach", color: "#fef7ee" },
  { name: "Sky Wash", color: "#f0f9ff" },
  { name: "Mint Cream", color: "#f0fdf4" },
];

const WALLPAPERS = [
  { id: "aurora-waves", name: "Aurora", gradient: "linear-gradient(135deg, #1a0533, #0a1628, #051a1a)" },
  { id: "nebula-depth", name: "Nebula", gradient: "linear-gradient(135deg, #1a0520, #0a0a30, #150525)" },
  { id: "ocean-floor", name: "Ocean", gradient: "linear-gradient(135deg, #020a18, #041828, #031020)" },
  { id: "solar-flare", name: "Solar", gradient: "linear-gradient(135deg, #1a0800, #200a0a, #180500)" },
  { id: "emerald-forest", name: "Forest", gradient: "linear-gradient(135deg, #020a08, #041810, #031208)" },
  { id: "cosmic-dust", name: "Cosmic", gradient: "linear-gradient(135deg, #0a0518, #100820, #0c0518)" },
];

const FONTS = [
  { id: "space", name: "Space Grotesk", preview: "Modern geometric", family: "'Space Grotesk', sans-serif" },
  { id: "inter", name: "Inter", preview: "Clean & neutral", family: "'Inter', sans-serif" },
  { id: "mono", name: "JetBrains Mono", preview: "Developer feel", family: "'JetBrains Mono', monospace" },
  { id: "rounded", name: "Nunito", preview: "Soft & friendly", family: "'Nunito', sans-serif" },
  { id: "elegant", name: "Playfair Display", preview: "Elegant serif", family: "'Playfair Display', serif" },
];

const ICON_SIZES = [
  { value: "normal", label: "Normal" },
  { value: "large", label: "Large (No Labels)" },
];

const BACKGROUND_EFFECTS = [
  { value: "animated", label: "Animated", icon: "~" },
  { value: "particles", label: "Particles", icon: "·" },
  { value: "flow", label: "Flow", icon: "≈" },
  { value: "stars", label: "Stars", icon: "*" },
  { value: "rings", label: "Rings", icon: "◎" },
];

const THREE_D_EFFECTS = [
  { value: "off", label: "Off", icon: "-" },
  { value: "subtle", label: "Subtle", icon: "◇" },
  { value: "dynamic", label: "Dynamic", icon: "✧" },
];

const CustomizePanel = ({ open, onClose, config, onConfigChange }) => {
  const fileRef = useRef(null);
  const wpFileRef = useRef(null);
  if (!open) return null;

  const update = (key, value) => onConfigChange({ ...config, [key]: value });

  const resizeImage = (file, maxWidth, maxHeight, quality) => {
    return new Promise((resolve) => {
      const reader = new FileReader();
      reader.onload = (e) => {
        const img = new Image();
        img.onload = () => {
          const canvas = document.createElement("canvas");
          let w = img.width;
          let h = img.height;
          if (w > maxWidth) { h = h * maxWidth / w; w = maxWidth; }
          if (h > maxHeight) { w = w * maxHeight / h; h = maxHeight; }
          canvas.width = w;
          canvas.height = h;
          canvas.getContext("2d").drawImage(img, 0, 0, w, h);
          resolve(canvas.toDataURL("image/jpeg", quality));
        };
        img.src = e.target.result;
      };
      reader.readAsDataURL(file);
    });
  };

  const handleWallpaperUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    try {
      const dataUrl = await resizeImage(file, 1200, 800, 0.75);
      onConfigChange({ ...config, customWallpaper: dataUrl, wallpaper: "custom" });
    } catch (err) { console.error("Wallpaper upload failed:", err); }
    e.target.value = "";
  };

  const handleBgColorUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    try {
      const dataUrl = await resizeImage(file, 800, 800, 0.7);
      update("customBgColor", dataUrl);
      update("bgColor", "custom");
    } catch (err) { console.error("BG color upload failed:", err); }
    e.target.value = "";
  };

  return (
    <>
      <div className={`customize-overlay ${open ? "visible" : ""}`} onClick={onClose} />
      <div className={`customize-panel ${open ? "open" : ""}`}>
        <div className="customize-header">
          <h2>Customize</h2>
          <button className="customize-close" onClick={onClose}>{"\u2715"}</button>
        </div>

        <div className="customize-section">
          <div className="customize-section-title">Icon Tint</div>
          <div className="tint-grid">
            {TINT_COLORS.map((t) => (
              <button
                key={t.name}
                className={`tint-swatch ${config.tint === t.name ? "active" : ""}`}
                style={{ background: t.color, "--swatch-color": t.color }}
                onClick={() => update("tint", t.name)}
                title={t.name}
              />
            ))}
          </div>
        </div>

        <div className="customize-section">
          <div className="customize-section-title">Background Color</div>
          <div className="tint-grid">
            {BG_COLORS.map((c) => (
              <button
                key={c.name}
                className={`tint-swatch ${config.bgColor === c.name ? "active" : ""}`}
                style={{
                  background: c.color || "linear-gradient(135deg, #09090b, #18181b)",
                  "--swatch-color": c.color || "#18181b",
                }}
                onClick={() => update("bgColor", c.name)}
                title={c.name}
              />
            ))}
            <button
              className={`tint-swatch tint-swatch-upload ${config.bgColor === "custom" ? "active" : ""}`}
              style={{
                background: config.customBgColor || "repeating-conic-gradient(#333 0% 25%, #222 0% 50%) 50% / 12px 12px",
                "--swatch-color": config.customBgColor || "#333",
              }}
              onClick={() => fileRef.current?.click()}
              title="Upload custom color"
            >
              <span className="swatch-plus">{"\u2795"}</span>
            </button>
            <input ref={fileRef} type="file" accept="image/*" hidden onChange={handleBgColorUpload} />
          </div>
        </div>

        <div className="customize-section">
          <div className="customize-section-title">Appearance</div>
          <div className="mode-options">
            <button className={`mode-option ${config.glassMode === "default" ? "active" : ""}`}
              onClick={() => update("glassMode", "default")}>
              <div className="mode-icon">{"\uD83D\uDC8E"}</div>
              Glass
            </button>
            <button className={`mode-option ${config.glassMode === "clear" ? "active" : ""}`}
              onClick={() => update("glassMode", "clear")}>
              <div className="mode-icon">{"\u2728"}</div>
              Clear
            </button>
            <button className={`mode-option ${config.glassMode === "dark" ? "active" : ""}`}
              onClick={() => update("glassMode", "dark")}>
              <div className="mode-icon">{"\uD83C\uDF19"}</div>
              Dark Icons
            </button>
          </div>
        </div>

        <div className="customize-section">
          <div className="customize-section-title">Icon Size</div>
          <div className="mode-options">
            {ICON_SIZES.map((s) => (
              <button key={s.value} className={`mode-option ${config.iconSize === s.value ? "active" : ""}`}
                onClick={() => update("iconSize", s.value)}>
                <div className="mode-icon" style={{ fontSize: s.value === "large" ? "24px" : "16px" }}>
                  {"\uD83D\uDCC1"}
                </div>
                {s.label}
              </button>
            ))}
          </div>
        </div>

        <div className="customize-section">
          <div className="customize-section-title">Wallpaper</div>
          <div className="wallpaper-grid">
            {WALLPAPERS.map((w) => (
              <button key={w.id}
                className={`wallpaper-thumb ${config.wallpaper === w.id ? "active" : ""}`}
                onClick={() => onConfigChange({ ...config, wallpaper: w.id, customWallpaper: null })}>
                <div className="wp-preview" style={{ background: w.gradient }} />
                <span className="wp-label">{w.name}</span>
              </button>
            ))}
            {config.customWallpaper && (
              <button
                className={`wallpaper-thumb ${config.wallpaper === "custom" ? "active" : ""}`}
                onClick={() => update("wallpaper", "custom")}
              >
                <div className="wp-preview" style={{ backgroundImage: `url(${config.customWallpaper})`, backgroundSize: "cover", backgroundPosition: "center" }} />
                <span className="wp-label">Custom</span>
              </button>
            )}
            <button
              className="wallpaper-thumb wallpaper-upload"
              onClick={() => wpFileRef.current?.click()}
            >
              <div className="wp-preview wp-upload-preview">
                <span className="upload-icon">{"\u2B06\uFE0F"}</span>
                <span className="upload-text">Upload</span>
              </div>
            </button>
            <input ref={wpFileRef} type="file" accept="image/*" hidden onChange={handleWallpaperUpload} />
          </div>
        </div>

        <div className="customize-section">
          <div className="customize-section-title">Background Effects</div>
          <div className="mode-options">
            {BACKGROUND_EFFECTS.map((effect) => (
              <button key={effect.value} className={`mode-option ${config.backgroundEffects === effect.value ? "active" : ""}`}
                onClick={() => update("backgroundEffects", effect.value)}>
                <div className="mode-icon">{effect.icon}</div>
                {effect.label}
              </button>
            ))}
          </div>
        </div>

        <div className="customize-section">
          <div className="customize-section-title">3D Effects</div>
          <div className="mode-options">
            {THREE_D_EFFECTS.map((effect) => (
              <button key={effect.value} className={`mode-option ${config.threeDEffects === effect.value ? "active" : ""}`}
                onClick={() => update("threeDEffects", effect.value)}>
                <div className="mode-icon">{effect.icon}</div>
                {effect.label}
              </button>
            ))}
          </div>
        </div>

        <div className="customize-section">
          <div className="customize-section-title">Font</div>
          <div className="font-options">
            {FONTS.map((f) => (
              <button key={f.id}
                className={`font-option ${config.font === f.id ? "active" : ""}`}
                onClick={() => update("font", f.id)}
                style={{ fontFamily: f.family }}>
                <span className="font-name">{f.name}</span>
                <span className="font-preview">{f.preview}</span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </>
  );
};

export default CustomizePanel;
export { TINT_COLORS, BG_COLORS, WALLPAPERS, FONTS, ICON_SIZES, BACKGROUND_EFFECTS, THREE_D_EFFECTS };
