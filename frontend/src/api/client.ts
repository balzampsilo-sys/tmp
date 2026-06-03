import type { Deck, DueCard, DueCount, HeatmapEntry, ReviewResponse, Stats } from "../types";

const BASE = import.meta.env.VITE_API_URL ?? "/api";

let _token: string | null = null;

export function setToken(t: string) {
  _token = t;
}

async function req<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string>),
  };
  if (_token) headers["Authorization"] = `Bearer ${_token}`;

  const res = await fetch(`${BASE}${path}`, { ...init, headers });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Request failed");
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

// ── Auth ──────────────────────────────────────────────────────────────────────

export async function authTelegram(initData: string) {
  return req<{ access_token: string; user: { id: string; first_name: string } }>(
    "/auth/telegram",
    { method: "POST", body: JSON.stringify({ init_data: initData }) },
  );
}

// ── Decks ─────────────────────────────────────────────────────────────────────

export const getDecks    = (level?: string) =>
  req<Deck[]>(`/decks${level ? `?level=${level}` : ""}`);

export const enrollDeck  = (id: string) =>
  req<void>(`/decks/${id}/enroll`, { method: "POST" });

export const unenrollDeck = (id: string) =>
  req<void>(`/decks/${id}/enroll`, { method: "DELETE" });

// ── Study ─────────────────────────────────────────────────────────────────────

export const getDueCount = () => req<DueCount>("/study/due/count");

export const getDueCards = (limit = 20) =>
  req<DueCard[]>(`/study/due?limit=${limit}`);

export const submitReview = (card_id: string, rating: number, elapsed_ms?: number) =>
  req<ReviewResponse>("/study/review", {
    method: "POST",
    body: JSON.stringify({ card_id, rating, elapsed_ms }),
  });

// ── Stats ─────────────────────────────────────────────────────────────────────

export const getStats   = () => req<Stats>("/stats/me");
export const getHeatmap = () => req<{ entries: HeatmapEntry[] }>("/stats/me/heatmap");
