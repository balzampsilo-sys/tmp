import { create } from "zustand";
import { setToken } from "../api/client";

interface AuthState {
  token:     string | null;
  userId:    string | null;
  firstName: string | null;
  ready:     boolean;
  setAuth: (token: string, userId: string, firstName: string) => void;
  setReady: () => void;
}

export const useAuth = create<AuthState>((set) => ({
  token:     null,
  userId:    null,
  firstName: null,
  ready:     false,
  setAuth: (token, userId, firstName) => {
    setToken(token);
    set({ token, userId, firstName });
  },
  setReady: () => set({ ready: true }),
}));
