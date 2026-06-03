import { useEffect, useState } from "react";
import { getHeatmap, getStats } from "../api/client";
import type { HeatmapEntry, Stats } from "../types";

export default function Stats() {
  const [stats,   setStats]   = useState<Stats | null>(null);
  const [heatmap, setHeatmap] = useState<HeatmapEntry[]>([]);

  useEffect(() => {
    getStats().then(setStats).catch(console.error);
    getHeatmap().then(({ entries }) => setHeatmap(entries)).catch(console.error);
  }, []);

  return (
    <div className="p-4 space-y-4">
      <h1 className="text-2xl font-bold text-tg-text pt-2">Прогресс</h1>

      {stats ? (
        <>
          {/* Streak banner */}
          {stats.streak_days > 0 && (
            <div className="rounded-2xl bg-orange-500/10 p-4 flex items-center gap-3">
              <span className="text-3xl">🔥</span>
              <div>
                <p className="font-bold text-tg-text">{stats.streak_days} дней подряд</p>
                <p className="text-xs text-tg-hint">Не останавливайся!</p>
              </div>
            </div>
          )}

          {/* Cards grid */}
          <div className="grid grid-cols-2 gap-3">
            <BigStat icon="✅" value={stats.cards_mastered}  label="Выучено" />
            <BigStat icon="📖" value={stats.cards_learning}  label="Учу сейчас" />
            <BigStat icon="🎯" value={`${Math.round(stats.retention_rate * 100)}%`} label="Запоминание" />
            <BigStat icon="🔢" value={stats.reviews_total}   label="Всего повторений" />
          </div>

          {/* Today */}
          <div className="rounded-2xl bg-tg-sec-bg p-4">
            <p className="text-sm text-tg-hint mb-1">Сегодня</p>
            <p className="text-2xl font-bold text-tg-text">
              {stats.reviews_today} <span className="text-base font-normal text-tg-hint">повторений</span>
            </p>
          </div>

          {/* Enrolled */}
          <div className="rounded-2xl bg-tg-sec-bg p-4">
            <p className="text-sm text-tg-hint mb-1">В обучении</p>
            <p className="text-2xl font-bold text-tg-text">
              {stats.total_cards_enrolled} <span className="text-base font-normal text-tg-hint">карточек</span>
            </p>
          </div>
        </>
      ) : (
        <div className="flex justify-center py-8">
          <div className="w-8 h-1 rounded-full bg-tg-btn animate-pulse" />
        </div>
      )}

      {/* Activity heatmap */}
      {heatmap.length > 0 && <ActivityHeatmap entries={heatmap} />}
    </div>
  );
}

function BigStat({ icon, value, label }: { icon: string; value: number | string; label: string }) {
  return (
    <div className="rounded-2xl bg-tg-sec-bg p-4">
      <p className="text-xl mb-1">{icon}</p>
      <p className="text-2xl font-bold text-tg-text">{value}</p>
      <p className="text-xs text-tg-hint mt-0.5">{label}</p>
    </div>
  );
}

function ActivityHeatmap({ entries }: { entries: HeatmapEntry[] }) {
  // Build last 12 weeks (84 days)
  const today = new Date();
  const days: { date: string; count: number }[] = [];
  for (let i = 83; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(d.getDate() - i);
    const key = d.toISOString().slice(0, 10);
    const found = entries.find((e) => e.date === key);
    days.push({ date: key, count: found?.count ?? 0 });
  }

  const maxCount = Math.max(...days.map((d) => d.count), 1);

  function cellColor(count: number) {
    if (count === 0) return "bg-tg-sec-bg";
    const level = Math.ceil((count / maxCount) * 4);
    return [
      "bg-tg-btn/25",
      "bg-tg-btn/45",
      "bg-tg-btn/70",
      "bg-tg-btn",
    ][level - 1];
  }

  // Group into weeks (columns of 7)
  const weeks: typeof days[] = [];
  for (let i = 0; i < days.length; i += 7) {
    weeks.push(days.slice(i, i + 7));
  }

  return (
    <div className="rounded-2xl bg-tg-sec-bg p-4">
      <p className="text-sm text-tg-hint mb-3">Активность (12 недель)</p>
      <div className="flex gap-1">
        {weeks.map((week, wi) => (
          <div key={wi} className="flex flex-col gap-1 flex-1">
            {week.map((day) => (
              <div
                key={day.date}
                title={`${day.date}: ${day.count}`}
                className={`aspect-square rounded-sm ${cellColor(day.count)}`}
              />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
