import React, { useState, useEffect, useCallback } from "react";
import { BrowserRouter as Router, Routes, Route, Link, useLocation, useNavigate, Navigate } from "react-router-dom";
import "./App.css";
import { AuthProvider, useAuth } from "./context/AuthContext";
import LoginPage from "./components/LoginPage";
import RegisterPage from "./components/RegisterPage";
import ProjectList from "./components/ProjectList";
import TaskList from "./components/TaskList";
import ExpenseDashboard from "./components/ExpenseDashboard";
import CustomizePanel, { TINT_COLORS } from "./components/CustomizePanel";

const THEMES = [
  { id: "dark", name: "Dark", icon: "\uD83C\uDF19" },
  { id: "light", name: "Light", icon: "\u2600\uFE0F" },
  { id: "glass", name: "Liquid Glass", icon: "\uD83D\uDC8E" },
  { id: "midnight", name: "Midnight", icon: "\uD83C\uDF0C" },
  { id: "forest", name: "Forest", icon: "\uD83C\uDF3F" },
  { id: "ocean", name: "Ocean", icon: "\uD83C\uDF0A" },
  { id: "lavender", name: "Lavender", icon: "\uD83D\uDC9C" },
];

const THEME_COLORS = {
  dark: "#a78bfa", light: "#7c3aed", glass: "#c8b4ff", midnight: "#818cf8",
  forest: "#34d399", ocean: "#38bdf8", lavender: "#a78bfa",
};

const ProtectedRoute = ({ children }) => {
  const { isAuthenticated, loading } = useAuth();
  if (loading) {
    return (
      <div className="auth-loading">
        <span className="spinner" style={{ width: 32, height: 32 }} />
      </div>
    );
  }
  return isAuthenticated ? children : <Navigate to="/login" replace />;
};

const PublicRoute = ({ children }) => {
  const { isAuthenticated, loading } = useAuth();
  if (loading) {
    return (
      <div className="auth-loading">
        <span className="spinner" style={{ width: 32, height: 32 }} />
      </div>
    );
  }
  return isAuthenticated ? <Navigate to="/" replace /> : children;
};

const LogoutButton = () => {
  const { logout, user } = useAuth();
  const navigate = useNavigate();
  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };
  return (
    <div className="sidebar-user">
      <div className="user-info">
        <div className="user-avatar">
          {user?.first_name?.[0] || user?.username?.[0] || "U"}
        </div>
        <div className="user-details">
          <span className="user-name">{user?.first_name || user?.username}</span>
          <span className="user-email">{user?.email}</span>
        </div>
      </div>
      <button className="btn btn-ghost btn-sm logout-btn" onClick={handleLogout}>
        {String.fromCodePoint(0x1F6AA)} Logout
      </button>
    </div>
  );
};

const AuthThemeSwitcher = ({ currentTheme, onChange }) => {
  return (
    <div className="auth-theme-bar">
      {THEMES.map((t) => (
        <button
          key={t.id}
          className={`auth-theme-dot ${currentTheme === t.id ? "active" : ""}`}
          style={{ background: THEME_COLORS[t.id] }}
          onClick={() => onChange(t.id)}
          data-tooltip={t.name}
          title={t.name}
        />
      ))}
    </div>
  );
};

const NavLink = ({ to, icon, children }) => {
  const location = useLocation();
  const isActive = location.pathname === to;
  return (
    <Link to={to} className={`nav-link ${isActive ? "active" : ""}`}>
      <span className="nav-icon">{icon}</span>
      <span>{children}</span>
    </Link>
  );
};

const AppLayout = ({ theme, setTheme, config, setConfig, panelOpen, setPanelOpen }) => {
  const { isAuthenticated, loading } = useAuth();
  if (loading) {
    return (
      <div className="auth-loading">
        <span className="spinner" style={{ width: 32, height: 32 }} />
      </div>
    );
  }
  if (!isAuthenticated) {
    return (
      <>
        <div className="auth-theme-switcher">
          <AuthThemeSwitcher currentTheme={theme} onChange={setTheme} />
        </div>
        <Routes>
          <Route path="/login" element={<PublicRoute><LoginPage /></PublicRoute>} />
          <Route path="/register" element={<PublicRoute><RegisterPage /></PublicRoute>} />
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </>
    );
  }
  return (
    <div className="app-layout">
      <aside className="sidebar">
        <div className="sidebar-logo">
          <Logo />
          <div className="sidebar-logo-text">
            <h1>Project Manager</h1>
            <p>AI-Powered Student Projects</p>
          </div>
        </div>
        <nav className="sidebar-nav">
          <NavLink to="/" icon={String.fromCodePoint(0x1F4C1)}>Projects</NavLink>
          <NavLink to="/tasks" icon={String.fromCodePoint(0x2705)}>Tasks</NavLink>
          <NavLink to="/expenses" icon={String.fromCodePoint(0x1F4B0)}>Expenses</NavLink>
        </nav>
        <LogoutButton />
        <ThemeSwitcher currentTheme={theme} onChange={setTheme} />
      </aside>
      <main className="main-content">
        <Routes>
          <Route path="/" element={<ProtectedRoute><ProjectList /></ProtectedRoute>} />
          <Route path="/tasks" element={<ProtectedRoute><TaskList /></ProtectedRoute>} />
          <Route path="/expenses" element={<ProtectedRoute><ExpenseDashboard /></ProtectedRoute>} />
          <Route path="/login" element={<Navigate to="/" replace />} />
          <Route path="/register" element={<Navigate to="/" replace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
      {theme === "glass" && (
        <>
          <button className="customize-toggle" onClick={() => setPanelOpen(true)} title="Customize">
            {"\u2699\uFE0F"}
          </button>
          <CustomizePanel
            open={panelOpen}
            onClose={() => setPanelOpen(false)}
            config={config}
            onConfigChange={setConfig}
          />
        </>
      )}
    </div>
  );
};

const ThemeSwitcher = ({ currentTheme, onChange }) => {
  const [open, setOpen] = useState(false);
  const ref = React.useRef(null);
  useEffect(() => {
    const close = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);
  const current = THEMES.find((t) => t.id === currentTheme);
  return (
    <div className="theme-section" ref={ref}>
      <button className="theme-trigger" onClick={() => setOpen(!open)}>
        <span className="theme-trigger-dot" style={{ background: THEME_COLORS[currentTheme] }} />
        <span className="theme-trigger-name">{current?.icon} {current?.name}</span>
        <span className={`theme-trigger-arrow ${open ? "open" : ""}`}>{"\u25BE"}</span>
      </button>
      {open && (
        <div className="theme-dropdown">
          {THEMES.map((t) => (
            <button key={t.id} className={`theme-option ${currentTheme === t.id ? "active" : ""}`}
              onClick={() => { onChange(t.id); setOpen(false); }}>
              <span className="theme-option-dot" style={{ background: THEME_COLORS[t.id] }} />
              <span>{t.icon} {t.name}</span>
              {currentTheme === t.id && <span className="theme-check">{"\u2713"}</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

const Logo = () => (
  <svg width="40" height="40" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
    <defs>
      <linearGradient id="logoGrad1" x1="0" y1="0" x2="40" y2="40">
        <stop offset="0%" stopColor="var(--accent)" />
        <stop offset="100%" stopColor="var(--bg-art-3)" />
      </linearGradient>
      <linearGradient id="logoGrad2" x1="0" y1="40" x2="40" y2="0">
        <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.25" />
        <stop offset="100%" stopColor="var(--bg-art-2)" stopOpacity="0.08" />
      </linearGradient>
      <filter id="logoGlow">
        <feGaussianBlur stdDeviation="1.2" result="blur" />
        <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
      </filter>
    </defs>
    <rect width="40" height="40" rx="11" fill="url(#logoGrad2)" />
    <rect x="0.5" y="0.5" width="39" height="39" rx="10.5" stroke="url(#logoGrad1)" strokeOpacity="0.35" />
    <path d="M11 14.5C11 13.4 11.9 12.5 13 12.5H17C18.1 12.5 19 13.4 19 14.5V16C19 17.1 18.1 18 17 18H13C11.9 18 11 17.1 11 16V14.5Z" fill="var(--accent)" opacity="0.85" filter="url(#logoGlow)" />
    <path d="M21 14.5C21 13.4 21.9 12.5 23 12.5H27C28.1 12.5 29 13.4 29 14.5V16C29 17.1 28.1 18 27 18H23C21.9 18 21 17.1 21 16V14.5Z" fill="var(--bg-art-3)" opacity="0.75" filter="url(#logoGlow)" />
    <path d="M11 23.5C11 22.4 11.9 21.5 13 21.5H17C18.1 21.5 19 22.4 19 23.5V25C19 26.1 18.1 27 17 27H13C11.9 27 11 26.1 11 25V23.5Z" fill="var(--bg-art-2)" opacity="0.55" filter="url(#logoGlow)" />
    <path d="M21 23.5C21 22.4 21.9 21.5 23 21.5H27C28.1 21.5 29 22.4 29 23.5V25C29 26.1 28.1 27 27 27H23C21.9 27 21 26.1 21 25V23.5Z" fill="var(--accent)" opacity="0.45" filter="url(#logoGlow)" />
    <circle cx="32" cy="9" r="1.8" fill="var(--accent)" opacity="0.7">
      <animate attributeName="opacity" values="0.7;1;0.7" dur="3s" repeatCount="indefinite" />
    </circle>
    <circle cx="8" cy="32" r="1.2" fill="var(--bg-art-3)" opacity="0.4">
      <animate attributeName="opacity" values="0.4;0.7;0.4" dur="4s" repeatCount="indefinite" />
    </circle>
  </svg>
);

const AbstractBackground = () => (
  <div className="bg-art">
    <div className="bg-orb bg-orb-1" />
    <div className="bg-orb bg-orb-2" />
    <div className="bg-orb bg-orb-3" />
    <div className="bg-orb bg-orb-4" />
    <div className="bg-grid" />
    <div className="bg-diagonal" />
    <div className="bg-line bg-line-1" />
    <div className="bg-line bg-line-2" />
    <div className="bg-shape bg-shape-1" />
    <div className="bg-shape bg-shape-2" />
    <div className="bg-shape bg-shape-3" />
    <div className="bg-shape bg-shape-4" />
    <div className="bg-glow" />
    <div className="bg-rings" />
    <div className="bg-particles">
      {[...Array(6)].map((_, i) => (
        <div key={i} className={`bg-particle bg-particle-${i + 1}`} />
      ))}
    </div>
  </div>
);

const DEFAULT_CONFIG = {
  tint: "Lavender",
  glassMode: "default",
  iconSize: "normal",
  wallpaper: "aurora-waves",
  backgroundEffects: "animated",
  threeDEffects: "subtle",
  font: "space",
  bgColor: "Default",
  customBgColor: null,
  customWallpaper: null,
};

const loadConfig = () => {
  try {
    const saved = localStorage.getItem("glassConfig");
    if (!saved) return DEFAULT_CONFIG;
    const config = { ...DEFAULT_CONFIG, ...JSON.parse(saved) };
    if (config.backgroundEffects === "full") config.backgroundEffects = "animated";
    return config;
  } catch { return DEFAULT_CONFIG; }
};

const App = () => {
  const [theme, setTheme] = useState(() => localStorage.getItem("theme") || "dark");
  const [config, setConfig] = useState(loadConfig);
  const [panelOpen, setPanelOpen] = useState(false);

  const applyConfig = useCallback((cfg) => {
    const root = document.documentElement;
    const tint = TINT_COLORS.find((t) => t.name === cfg.tint) || TINT_COLORS[0];

    root.style.setProperty("--icon-tint", tint.color);
    root.style.setProperty("--icon-tint-light", tint.color + "dd");
    root.style.setProperty("--icon-tint-mid", tint.color + "aa");
    root.style.setProperty("--icon-tint-glow", tint.glow);
    root.style.setProperty("--icon-tint-hue", tint.hue + "deg");

    root.setAttribute("data-glass-mode", cfg.glassMode);
    root.setAttribute("data-glass-icons", cfg.iconSize);
    root.setAttribute("data-wallpaper", cfg.wallpaper);
    root.setAttribute("data-background-effects", cfg.backgroundEffects || "full");
    root.setAttribute("data-3d-effects", cfg.threeDEffects || "subtle");
    root.setAttribute("data-font", cfg.font);

    const fontMap = {
      space: "'Space Grotesk', sans-serif",
      inter: "'Inter', sans-serif",
      mono: "'JetBrains Mono', monospace",
      rounded: "'Nunito', sans-serif",
      elegant: "'Playfair Display', serif",
    };
    root.style.setProperty("--app-font", fontMap[cfg.font] || fontMap.space);

    const hexToRgb = (hex) => {
      hex = hex.replace("#", "");
      if (hex.length === 3) hex = hex[0]+hex[0]+hex[1]+hex[1]+hex[2]+hex[2];
      return { r: parseInt(hex.substring(0, 2), 16), g: parseInt(hex.substring(2, 4), 16), b: parseInt(hex.substring(4, 6), 16) };
    };

    const isLight = (hex) => {
      const { r, g, b } = hexToRgb(hex);
      return (r * 299 + g * 587 + b * 114) / 1000 > 140;
    };

    const bgColors = {
      "Default": null, "Charcoal": "#1a1a2e", "Navy": "#0f1b2d",
      "Deep Purple": "#160a2e", "Midnight Blue": "#0a1929", "Slate": "#1e293b",
      "Obsidian": "#0d0d0d", "Warm Gray": "#1c1917", "Dark Teal": "#0a1f1c",
      "Rich Black": "#050510", "Espresso": "#1a0f0a", "Storm": "#151820",
      "Snow": "#f8fafc", "Ivory": "#fefdf5", "Linen": "#faf5ef",
      "Pearl": "#f0eef6", "Mist": "#eef2f7", "Cloud": "#f1f5f9",
      "Lavender Mist": "#f3f0ff", "Rose Quartz": "#fdf2f4", "Seafoam": "#f0fdf9",
      "Peach": "#fef7ee", "Sky Wash": "#f0f9ff", "Mint Cream": "#f0fdf4",
    };

    let bgColorValue = null;
    if (cfg.bgColor === "custom" && cfg.customBgColor) {
      bgColorValue = cfg.customBgColor;
    } else if (bgColors[cfg.bgColor]) {
      bgColorValue = bgColors[cfg.bgColor];
    }

    if (bgColorValue) {
      root.style.setProperty("--bg-primary", bgColorValue);
    } else {
      root.style.removeProperty("--bg-primary");
    }

    if (cfg.bgColor !== "Default" && bgColorValue) {
      const light = bgColorValue.startsWith("#") ? isLight(bgColorValue) : false;
      if (light) {
        root.style.setProperty("--text-primary", "#1a1625");
        root.style.setProperty("--text-secondary", "#4a4458");
        root.style.setProperty("--text-muted", "#8a849a");
        root.style.setProperty("--border", "rgba(60, 50, 80, 0.15)");
        root.style.setProperty("--bg-card", "rgba(255, 255, 255, 0.65)");
        root.style.setProperty("--bg-hover", "rgba(0, 0, 0, 0.04)");
        root.style.setProperty("--bg-input", "rgba(255, 255, 255, 0.8)");
        root.style.setProperty("--glass", "rgba(255, 255, 255, 0.5)");
        root.style.setProperty("--glass-border", "rgba(0, 0, 0, 0.06)");
      } else {
        root.style.setProperty("--text-primary", "#f0eef6");
        root.style.setProperty("--text-secondary", "#a8a4b8");
        root.style.setProperty("--text-muted", "#5a5670");
        root.style.setProperty("--border", "rgba(255, 255, 255, 0.08)");
        root.style.setProperty("--bg-card", "rgba(255, 255, 255, 0.04)");
        root.style.setProperty("--bg-hover", "rgba(255, 255, 255, 0.06)");
        root.style.setProperty("--bg-input", "rgba(255, 255, 255, 0.04)");
        root.style.setProperty("--glass", "rgba(255, 255, 255, 0.03)");
        root.style.setProperty("--glass-border", "rgba(255, 255, 255, 0.06)");
      }
    } else {
      root.style.removeProperty("--text-primary");
      root.style.removeProperty("--text-secondary");
      root.style.removeProperty("--text-muted");
      root.style.removeProperty("--border");
      root.style.removeProperty("--bg-card");
      root.style.removeProperty("--bg-hover");
      root.style.removeProperty("--bg-input");
      root.style.removeProperty("--glass");
      root.style.removeProperty("--glass-border");
    }
  }, []);

  useEffect(() => {
    const wp = document.querySelector(".bg-wallpaper");
    if (!wp) return;
    if (config.wallpaper === "custom" && config.customWallpaper) {
      wp.style.background = `url(${config.customWallpaper})`;
      wp.style.backgroundSize = "cover";
      wp.style.backgroundPosition = "center";
      wp.style.animation = "none";
      wp.style.opacity = "0.5";
    } else if (config.wallpaper && config.wallpaper !== "custom") {
      wp.style.background = "";
      wp.style.backgroundSize = "";
      wp.style.backgroundPosition = "";
      wp.style.animation = "";
      wp.style.opacity = "0.4";
    } else {
      wp.style.background = "";
      wp.style.backgroundSize = "";
      wp.style.backgroundPosition = "";
      wp.style.animation = "";
      wp.style.opacity = "0";
    }
  }, [config.wallpaper, config.customWallpaper]);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("theme", theme);
  }, [theme]);

  useEffect(() => {
    applyConfig(config);
    try {
      localStorage.setItem("glassConfig", JSON.stringify(config));
    } catch (e) {
      const fallback = { ...config, customWallpaper: null, customBgColor: null };
      try { localStorage.setItem("glassConfig", JSON.stringify(fallback)); } catch {}
    }
  }, [config, applyConfig]);

  useEffect(() => {
    if (theme !== "glass") return;
    let ticking = false;
    const onScroll = () => {
      if (!ticking) {
        window.requestAnimationFrame(() => {
          const scrollY = window.scrollY;
          const orbs = document.querySelectorAll(".bg-orb");
          orbs.forEach((orb, i) => {
            const speed = 0.02 + i * 0.008;
            const yOffset = scrollY * speed;
            const blur = 90 + scrollY * 0.03;
            orb.style.transform = `translateY(${-yOffset}px)`;
            orb.style.filter = `blur(${Math.min(blur, 130)}px)`;
          });
          const glow = document.querySelector(".bg-glow");
          if (glow) {
            const glowOpacity = 0.4 - scrollY * 0.0003;
            glow.style.opacity = Math.max(glowOpacity, 0.1);
          }
          ticking = false;
        });
        ticking = true;
      }
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [theme]);

  return (
    <Router>
      <AuthProvider>
        <div className="bg-wallpaper" />
        <AbstractBackground />
        <AppLayout theme={theme} setTheme={setTheme} config={config} setConfig={setConfig} panelOpen={panelOpen} setPanelOpen={setPanelOpen} />
      </AuthProvider>
    </Router>
  );
};

export default App;
