import type { Rating } from "../types";

interface Props {
  onRate: (r: Rating) => void;
  disabled?: boolean;
}

const RATINGS: { value: Rating; label: string; sub: string; cls: string }[] = [
  { value: 1, label: "Снова",   sub: "<1м",  cls: "bg-red-500/90 text-white" },
  { value: 2, label: "Сложно",  sub: "~10м", cls: "bg-orange-400/90 text-white" },
  { value: 3, label: "Хорошо",  sub: "~3д",  cls: "bg-emerald-500/90 text-white" },
  { value: 4, label: "Легко",   sub: "~2н",  cls: "bg-sky-500/90 text-white" },
];

export default function RatingBar({ onRate, disabled }: Props) {
  return (
    <div className="grid grid-cols-4 gap-2 px-2">
      {RATINGS.map(({ value, label, sub, cls }) => (
        <button
          key={value}
          disabled={disabled}
          onClick={() => onRate(value)}
          className={`${cls} rounded-2xl py-3 flex flex-col items-center gap-0.5
                      active:scale-95 transition-transform disabled:opacity-50`}
        >
          <span className="text-sm font-semibold">{label}</span>
          <span className="text-xs opacity-80">{sub}</span>
        </button>
      ))}
    </div>
  );
}
