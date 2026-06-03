import { useRef } from "react";
import type { DueCard } from "../types";

interface Props {
  card: DueCard;
  flipped: boolean;
  onFlip: () => void;
}

export default function FlashCard({ card, flipped, onFlip }: Props) {
  const audioRef = useRef<HTMLAudioElement | null>(null);

  function playAudio() {
    if (!card.audio_url) return;
    if (!audioRef.current) {
      audioRef.current = new Audio(card.audio_url);
    }
    audioRef.current.currentTime = 0;
    audioRef.current.play().catch(() => {});
  }

  return (
    <div
      className="card-scene w-full"
      style={{ height: "clamp(280px, 52vw, 360px)" }}
      onClick={!flipped ? onFlip : undefined}
    >
      <div className={`card-body rounded-3xl shadow-lg ${flipped ? "flipped" : ""}`}>
        {/* Front */}
        <div className="card-face bg-tg-sec-bg rounded-3xl flex flex-col items-center justify-center p-6 gap-3">
          {!flipped && (
            <p className="text-xs text-tg-hint uppercase tracking-widest">
              {card.cefr_level ?? ""}
            </p>
          )}
          <p className="text-4xl font-bold text-tg-text text-center">{card.front}</p>
          {card.ipa && (
            <p className="text-tg-hint text-lg">{card.ipa}</p>
          )}
          {card.audio_url && (
            <button
              onClick={(e) => { e.stopPropagation(); playAudio(); }}
              className="mt-1 text-tg-btn text-2xl active:scale-90 transition-transform"
            >
              🔊
            </button>
          )}
          {!flipped && (
            <p className="text-tg-hint text-sm mt-2">Нажми, чтобы открыть</p>
          )}
        </div>

        {/* Back */}
        <div className="card-back card-face bg-tg-sec-bg rounded-3xl flex flex-col p-6 gap-3 overflow-y-auto">
          <div className="text-center">
            <p className="text-sm text-tg-hint">{card.front}</p>
            <p className="text-3xl font-bold text-tg-text mt-1">{card.back}</p>
            {card.pos && (
              <p className="text-xs text-tg-btn mt-1 uppercase tracking-wide">{card.pos}</p>
            )}
          </div>

          {card.examples[0] && (
            <div className="bg-tg-bg rounded-2xl p-3 mt-1 text-sm space-y-1">
              <p className="text-tg-text italic">"{card.examples[0].en}"</p>
              <p className="text-tg-hint">"{card.examples[0].ru}"</p>
            </div>
          )}

          {card.synonyms.length > 0 && (
            <p className="text-xs text-tg-hint text-center">
              = {card.synonyms.slice(0, 3).join(", ")}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
