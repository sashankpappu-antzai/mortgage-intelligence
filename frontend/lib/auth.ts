"use client";

import { create } from "zustand";

interface AuthUser {
  id: string;
  email: string;
  name: string;
  role: string;
}

interface AuthState {
  user: AuthUser | null;
  token: string | null;
  isLoading: boolean;
  setAuth: (user: AuthUser, token: string, refreshToken: string) => void;
  logout: () => void;
  hydrate: () => void;
}

export const useAuth = create<AuthState>((set) => ({
  user: null,
  token: null,
  isLoading: true,

  setAuth: (user, token, refreshToken) => {
    localStorage.setItem("access_token", token);
    localStorage.setItem("refresh_token", refreshToken);
    localStorage.setItem("user", JSON.stringify(user));
    set({ user, token, isLoading: false });
  },

  logout: () => {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    localStorage.removeItem("user");
    set({ user: null, token: null, isLoading: false });
  },

  hydrate: () => {
    const token = localStorage.getItem("access_token");
    const userStr = localStorage.getItem("user");
    if (token && userStr) {
      try {
        const user = JSON.parse(userStr);
        set({ user, token, isLoading: false });
      } catch {
        set({ isLoading: false });
      }
    } else {
      set({ isLoading: false });
    }
  },
}));
