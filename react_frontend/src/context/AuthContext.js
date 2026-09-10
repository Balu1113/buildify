import React, { createContext, useState, useContext, useEffect, useCallback } from "react";
import { authAPI } from "../services/api";

const AuthContext = createContext(null);

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
};

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const loadUser = useCallback(async () => {
    const access = localStorage.getItem("access_token");
    if (!access) {
      setLoading(false);
      return;
    }
    try {
      const response = await authAPI.profile();
      setUser(response.data);
    } catch {
      localStorage.removeItem("access_token");
      localStorage.removeItem("refresh_token");
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadUser();
  }, [loadUser]);

  const login = async (username, password) => {
    setError(null);
    try {
      const response = await authAPI.login({ username, password });
      const { user: userData, tokens } = response.data;
      localStorage.setItem("access_token", tokens.access);
      localStorage.setItem("refresh_token", tokens.refresh);
      setUser(userData);
      return userData;
    } catch (err) {
      const message = err.response?.data?.error || "Login failed. Please try again.";
      setError(message);
      throw new Error(message);
    }
  };

  const register = async (data) => {
    setError(null);
    try {
      const response = await authAPI.register(data);
      const { user: userData, tokens } = response.data;
      localStorage.setItem("access_token", tokens.access);
      localStorage.setItem("refresh_token", tokens.refresh);
      setUser(userData);
      return userData;
    } catch (err) {
      const errors = err.response?.data;
      let message = "Registration failed. Please try again.";
      if (errors) {
        if (typeof errors === "object") {
          const firstKey = Object.keys(errors)[0];
          const firstVal = Array.isArray(errors[firstKey]) ? errors[firstKey][0] : errors[firstKey];
          message = firstVal || message;
        }
      }
      setError(message);
      throw new Error(message);
    }
  };

  const logout = async () => {
    const refresh = localStorage.getItem("refresh_token");
    try {
      if (refresh) {
        await authAPI.logout({ refresh });
      }
    } catch {
      // Logout even if API call fails
    } finally {
      localStorage.removeItem("access_token");
      localStorage.removeItem("refresh_token");
      setUser(null);
    }
  };

  const updateProfile = async (data) => {
    try {
      const response = await authAPI.updateProfile(data);
      setUser(response.data);
      return response.data;
    } catch (err) {
      throw err;
    }
  };

  const value = {
    user,
    loading,
    error,
    login,
    register,
    logout,
    updateProfile,
    isAuthenticated: !!user,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export default AuthContext;
