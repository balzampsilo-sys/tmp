export default function Boot() {
  return (
    <div className="h-screen flex flex-col items-center justify-center gap-4 bg-tg-bg">
      <div className="w-12 h-12 rounded-2xl bg-tg-btn flex items-center justify-center text-2xl">
        🧠
      </div>
      <div className="w-8 h-1 rounded-full bg-tg-btn animate-pulse" />
    </div>
  );
}
