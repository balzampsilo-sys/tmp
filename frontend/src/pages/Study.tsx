import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getDueCards, submitReview } from "../api/client";
import FlashCard from "../components/FlashCard";
import RatingBar  from "../components/RatingBar";
import type { DueCard, Rating } from "../types";

type Phase = "loading" | "front" | "back" | "submitting" | "done";

export default function Study() {
  const navigate = useNavigate();

  const [cards,   setCards]   = useState<DueCard[]>([]);
  const [idx,     setIdx]     = useState(0);
  const [phase,   setPhase]   = useState<Phase>("loading");
  const [results, setResults] = useState<{ again: number; good: number }>({ again: 0, good: 0 });
  const startMs = useRef(Date.now());

  useEffect(() => {
    getDueCards(30)
      .then((data) => {
        setCards(data);
        setPhase(data.length === 0 ? "done" : "front");
      })
      .catch(() => setPhase("done"));
  }, []);

  const current = cards[idx];
  const total   = cards.length;
  const progress = total > 0 ? idx / total : 0;

  const handleFlip = useCallback(() => setPhase("back"), []);

  const handleRate = useCallback(async (rating: Rating) => {
    if (!current || phase === "submitting") return;
    setPhase("submitting");

    const elapsed = Date.now() - startMs.current;
    startMs.current = Date.now();

    try {
      await submitReview(current.id, rating, elapsed);
    } catch (e) {
      console.error(e);
    }

    setResults((r) => ({
      again: r.again + (rating === 1 ? 1 : 0),
      good:  r.good  + (rating >= 3 ? 1 : 0),
    }));

    const next = idx + 1;
    if (next >= total) {
      setPhase("done");
    } else {
      setIdx(next);
      setPhase("front");
    }
  }, [current, idx, total, phase]);

  if (phase === "loading") {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="w-8 h-1 rounded-full bg-tg-btn animate-pulse" />
      </div>
    );
  }

  if (phase === "done") {
    const reviewed = results.again + results.good;
    const accuracy = reviewed > 0 ? Math.round(results.good / reviewed * 100) : 0;
    return <Summary reviewed={reviewed} accuracy={accuracy} onHome={() => navigate("/")} />;
  }

  if (!current) return null;

  return (
    <div className="flex flex-col h-full p-4 gap-4">
      {/* Progress */}
      <div className="flex items-center gap-3 pt-2">
        <button
          onClick={() => navigate("/")}
          className="text-tg-hint text-lg px-1"
        >
          ←
        </button>
        <div className="flex-1 h-1.5 rounded-full bg-tg-sec-bg overflow-hidden">
          <div
            className="h-full bg-tg-btn rounded-full transition-all duration-300"
            style={{ width: `${progress * 100}%` }}
          />
        </div>
        <span className="text-xs text-tg-hint w-12 text-right">
          {idx + 1} / {total}
        </span>
      </div>

      {/* Card area */}
      <div className="flex-1 flex flex-col justify-center gap-4">
        <FlashCard
          card={current}
          flipped={phase === "back" || phase === "submitting"}
          onFlip={handleFlip}
        />

        {/* Hint when on front */}
        {phase === "front" && (
          <p className="text-center text-tg-hint text-sm">
            Вспомни перевод, затем нажми на карточку
          </p>
        )}
      </div>

      {/* Rating bar — only shown when card is revealed */}
      <div
        className={`transition-all duration-300 ${
          phase === "back" ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4 pointer-events-none"
        }`}
      >
        <p className="text-center text-xs text-tg-hint mb-2">Как хорошо ты вспомнил?</p>
        <RatingBar onRate={handleRate} disabled={phase !== "back"} />
      </div>
    </div>
  );
}

function Summary({ reviewed, accuracy, onHome }: {
  reviewed: number; accuracy: number; onHome: () => void;
}) {
  return (
    <div className="h-full flex flex-col items-center justify-center p-6 gap-6 text-center">
      <p className="text-6xl">{accuracy >= 80 ? "🎉" : accuracy >= 50 ? "💪" : "📖"}</p>
      <div>
        <h2 className="text-2xl font-bold text-tg-text">Сессия завершена!</h2>
        <p className="text-tg-hint mt-1">Повторено карточек: {reviewed}</p>
      </div>
      <div className="flex gap-6">
        <div className="text-center">
          <p className="text-3xl font-bold text-tg-btn">{accuracy}%</p>
          <p className="text-xs text-tg-hint">точность</p>
        </div>
        <div className="text-center">
          <p className="text-3xl font-bold text-tg-btn">{reviewed}</p>
          <p className="text-xs text-tg-hint">карточек</p>
        </div>
      </div>
      <button
        onClick={onHome}
        className="w-full max-w-xs py-4 rounded-2xl bg-tg-btn text-tg-btn-txt
                   font-semibold text-lg active:opacity-80 transition-opacity"
      >
        На главную
      </button>
    </div>
  );
}
