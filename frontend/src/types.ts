export interface Example {
  en: string;
  ru: string;
  source: string;
}

export interface DueCard {
  id: string;
  deck_id: string;
  front: string;
  back: string;
  ipa: string | null;
  pos: string | null;
  cefr_level: string | null;
  examples: Example[];
  synonyms: string[];
  audio_url: string | null;
  reps: number;
  lapses: number;
  state: "new" | "learning" | "review" | "relearning";
}

export interface Deck {
  id: string;
  name: string;
  description: string | null;
  cefr_level: string | null;
  tags: string[];
  card_count: number;
  source: "platform" | "tenant" | "personal";
  is_public: boolean;
  enrolled: boolean;
}

export interface Stats {
  total_cards_enrolled: number;
  cards_mastered: number;
  cards_learning: number;
  retention_rate: number;
  streak_days: number;
  reviews_today: number;
  reviews_total: number;
}

export interface HeatmapEntry {
  date: string;
  count: number;
}

export interface DueCount {
  new: number;
  learning: number;
  review: number;
  total: number;
}

export interface ReviewResponse {
  card_id: string;
  next_due: string;
  new_interval_days: number;
  new_stability: number;
  new_state: string;
}

// 1=Again 2=Hard 3=Good 4=Easy
export type Rating = 1 | 2 | 3 | 4;
