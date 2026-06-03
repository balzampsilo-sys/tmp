import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getDueCount, getStats } from "../api/client";
import { useAuth } from "../store";
import type { DueCount, Stats } from "../types";

export default function Home() {
  const { firstName } = useAuth();
  const navigate = useNavigate();

  const [due,   setDue]   = useState<DueCount | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);

  useEffect(() => {
    getDueCount().then(setDue).catch(console.error);
    getStats().then(setStats).catch(console.error);
  }, []);

  const total = due?.total ?? 0;

  return (
    <div className="p-4 space-y-4">
      {/* Header */}
      <div className="pt-2">
        <p className="text-tg-hint text-sm">Привет, {firstName ?? "друг"}!</p>
        <h1 className="text-2xl font-bold text-tg-text">English SRS</h1>
      </div>

      {/* Today's session card */}
      <button
        onClick={() => navigate("/study")}
        disabled={total === 0}
        className="w-full rounded-2xl bg-tg-btn text-tg-btn-txt p-5 text-left
                   active:opacity-80 transition-opacity disabled:opacity-40"
      >
        <p className="text-sm opacity-80 mb-1">На сегодня</p>
        <p className="text-4xl font-bold">{total}</p>
        <p className="text-sm opacity-80 mt-1">
          {total === 0 ? "Всё выучено 🎉" : "карточек к повторению"}
        </p>
        {due && total > 0 && (
          <div className="flex gap-3 mt-3 text-xs opacity-75">
            {due.new      > 0 && <span>🆕 {due.new} новых</span>}
            {due.learning > 0 && <span>📖 {due.learning} учу</span>}
            {due.review   > 0 && <span>🔄 {due.review} повторение</span>}
          </div>
        )}
      </button>

      {/* Stats row */}
      {stats && (
        <div className="grid grid-cols-3 gap-3">
          <StatCell
            icon="🔥"
            value={stats.streak_days}
            label="дней подряд"
          />
          <StatCell
            icon="✅"
            value={stats.cards_mastered}
            label="выучено"
          />
          <StatCell
            icon="🎯"
            value={`${Math.round(stats.retention_rate * 100)}%`}
            label="запоминание"
          />
        </div>
      )}

      {/* Quick links */}
      <div className="space-y-2">
        <QuickLink
          icon="📚"
          title="Каталог колод"
          sub="Добавить новые темы"
          onClick={() => navigate("/catalog")}
        />
        <QuickLink
          icon="📊"
          title="Мой прогресс"
          sub="История повторений"
          onClick={() => navigate("/stats")}
        />
      </div>
    </div>
  );
}

function StatCell({ icon, value, label }: { icon: string; value: number | string; label: string }) {
  return (
    <div className="rounded-2xl bg-tg-sec-bg p-3 text-center">
      <p className="text-2xl">{icon}</p>
      <p className="text-xl font-bold text-tg-text">{value}</p>
      <p className="text-xs text-tg-hint leading-tight mt-0.5">{label}</p>
    </div>
  );
}

function QuickLink({ icon, title, sub, onClick }: {
  icon: string; title: string; sub: string; onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="w-full flex items-center gap-3 p-4 rounded-2xl bg-tg-sec-bg
                 text-left active:opacity-70 transition-opacity"
    >
      <span className="text-2xl">{icon}</span>
      <div className="flex-1 min-w-0">
        <p className="font-medium text-tg-text">{title}</p>
        <p className="text-xs text-tg-hint">{sub}</p>
      </div>
      <span className="text-tg-hint">›</span>
    </button>
  );
}
