import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

const LoginPage = () => {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const { login, error } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!username.trim() || !password.trim()) return;
    setLoading(true);
    try {
      await login(username, password);
      navigate("/");
    } catch {
      // error is handled by AuthContext
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-container">
        <div className="auth-card animate-in">
          <div className="auth-header">
            <div className="auth-logo">
              <svg width="48" height="48" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
                <defs>
                  <linearGradient id="authLogoGrad" x1="0" y1="0" x2="40" y2="40">
                    <stop offset="0%" stopColor="var(--accent)" />
                    <stop offset="100%" stopColor="var(--bg-art-3)" />
                  </linearGradient>
                </defs>
                <rect width="40" height="40" rx="11" fill="var(--accent-glow)" />
                <rect x="0.5" y="0.5" width="39" height="39" rx="10.5" stroke="url(#authLogoGrad)" strokeOpacity="0.35" />
                <path d="M11 14.5C11 13.4 11.9 12.5 13 12.5H17C18.1 12.5 19 13.4 19 14.5V16C19 17.1 18.1 18 17 18H13C11.9 18 11 17.1 11 16V14.5Z" fill="var(--accent)" opacity="0.85" />
                <path d="M21 14.5C21 13.4 21.9 12.5 23 12.5H27C28.1 12.5 29 13.4 29 14.5V16C29 17.1 28.1 18 27 18H23C21.9 18 21 17.1 21 16V14.5Z" fill="var(--bg-art-3)" opacity="0.75" />
                <path d="M11 23.5C11 22.4 11.9 21.5 13 21.5H17C18.1 21.5 19 22.4 19 23.5V25C19 26.1 18.1 27 17 27H13C11.9 27 11 26.1 11 25V23.5Z" fill="var(--bg-art-2)" opacity="0.55" />
                <path d="M21 23.5C21 22.4 21.9 21.5 23 21.5H27C28.1 21.5 29 22.4 29 23.5V25C29 26.1 28.1 27 27 27H23C21.9 27 21 26.1 21 25V23.5Z" fill="var(--accent)" opacity="0.45" />
              </svg>
            </div>
            <h1 className="auth-title">Welcome Back</h1>
            <p className="auth-subtitle">Sign in to your account</p>
          </div>

          {error && <div className="toast toast-error">{error}</div>}

          <form onSubmit={handleSubmit} className="auth-form">
            <div className="form-group">
              <label className="form-label">Username</label>
              <input
                type="text"
                className="input"
                placeholder="Enter your username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                autoFocus
              />
            </div>

            <div className="form-group">
              <label className="form-label">Password</label>
              <div className="password-input-wrapper">
                <input
                  type={showPassword ? "text" : "password"}
                  className="input"
                  placeholder="Enter your password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
                <button
                  type="button"
                  className="password-toggle"
                  onClick={() => setShowPassword(!showPassword)}
                >
                  {showPassword ? "🙈" : "👁"}
                </button>
              </div>
            </div>

            <button type="submit" className="btn btn-primary btn-lg auth-submit" disabled={loading}>
              {loading ? <span className="spinner" /> : "Sign In"}
            </button>
          </form>

          <div className="auth-footer">
            <p>
              Don't have an account?{" "}
              <Link to="/register" className="auth-link">Create one</Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default LoginPage;
