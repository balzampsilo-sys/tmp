import { useEffect, useState } from "react";
import { enrollDeck, getDecks, unenrollDeck } from "../api/client";
import type { Deck } from "../types";

const LEVEL_BADGE: Record<string, string> = {
  A1: "bg-green-100  text-green-700",
  A2: "bg-green-200  text-green-800",
  B1: "bg-blue-100   text-blue-700",
  B2: "bg-blue-200   text-blue-800",
  C1: "bg-purple-100 text-purple-700",
  C2: "bg-purple-200 text-purple-800",
};

export default function Catalog() {
  const [decks,   setDecks]   = useState<Deck[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter,  setFilter]  = useState<string>("");

  useEffect(() => {
    getDecks()
      .then(setDecks)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  async function toggle(deck: Deck) {
    try {
      if (deck.enrolled) {
        await unenrollDeck(deck.id);
      } else {
        await enrollDeck(deck.id);
      }
      setDecks((ds) =>
        ds.map((d) => d.id === deck.id ? { ...d, enrolled: !d.enrolled } : d),
      );
    } catch (e) {
      console.error(e);
    }
  }

  const levels    = ["A1", "A2", "B1", "B2", "C1", "C2"];
  const displayed = filter
    ? decks.filter((d) => d.cefr_level === filter)
    : decks;

  return (
    <div className="p-4 space-y-4">
      <h1 className="text-2xl font-bold text-tg-text pt-2">Каталог колод</h1>

      {/* Level filter */}
      <div className="flex gap-2 overflow-x-auto pb-1 -mx-1 px-1">
        <Chip active={filter === ""} onClick={() => setFilter("")}>Все</Chip>
        {levels.map((l) => (
          <Chip key={l} active={filter === l} onClick={() => setFilter(l)}>{l}</Chip>
        ))}
      </div>

      {loading && (
        <div className="flex justify-center py-8">
          <div className="w-8 h-1 rounded-full bg-tg-btn animate-pulse" />
        </div>
      )}

      <div className="space-y-3">
        {displayed.map((deck) => (
          <DeckItem key={deck.id} deck={deck} onToggle={toggle} />
        ))}
        {!loading && displayed.length === 0 && (
          <p className="text-center text-tg-hint py-8">Колоды не найдены</p>
        )}
      </div>
    </div>
  );
}

function Chip({ active, onClick, children }: {
  active: boolean; onClick: () => void; children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex-shrink-0 px-3 py-1.5 rounded-full text-sm font-medium
                  transition-colors
                  ${active
                    ? "bg-tg-btn text-tg-btn-txt"
                    : "bg-tg-sec-bg text-tg-hint"
                  }`}
    >
      {children}
    </button>
  );
}

function DeckItem({ deck, onToggle }: { deck: Deck; onToggle: (d: Deck) => void }) {
  const badgeCls = deck.cefr_level ? LEVEL_BADGE[deck.cefr_level] ?? "" : "";

  return (
    <div className="flex items-center gap-3 p-4 rounded-2xl bg-tg-sec-bg">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-0.5">
          {deck.cefr_level && (
            <span className={`text-xs font-bold px-1.5 py-0.5 rounded ${badgeCls}`}>
              {deck.cefr_level}
            </span>
          )}
          <p className="font-medium text-tg-text truncate">{deck.name}</p>
        </div>
        <p className="text-xs text-tg-hint">{deck.card_count} карточек</p>
      </div>
      <button
        onClick={() => onToggle(deck)}
        className={`flex-shrink-0 px-4 py-2 rounded-xl text-sm font-medium transition-colors
                    ${deck.enrolled
                      ? "bg-tg-btn/10 text-tg-btn"
                      : "bg-tg-btn text-tg-btn-txt"
                    }`}
      >
        {deck.enrolled ? "Добавлена" : "Добавить"}
      </button>
    </div>
  );
}
