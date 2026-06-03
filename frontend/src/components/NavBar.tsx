import { NavLink } from "react-router-dom";

const tabs = [
  { to: "/",        icon: "🏠", label: "Главная" },
  { to: "/study",   icon: "⚡", label: "Учить" },
  { to: "/catalog", icon: "📚", label: "Колоды" },
  { to: "/stats",   icon: "📊", label: "Прогресс" },
];

export default function NavBar() {
  return (
    <nav className="fixed bottom-0 left-0 right-0 max-w-md mx-auto
                    bg-tg-sec-bg border-t border-tg-hint/20
                    flex items-stretch h-16 z-50">
      {tabs.map(({ to, icon, label }) => (
        <NavLink
          key={to}
          to={to}
          end={to === "/"}
          className={({ isActive }) =>
            `flex-1 flex flex-col items-center justify-center gap-0.5 text-xs transition-colors
             ${isActive ? "text-tg-btn" : "text-tg-hint"}`
          }
        >
          <span className="text-xl leading-none">{icon}</span>
          <span>{label}</span>
        </NavLink>
      ))}
    </nav>
  );
}
