import { useEffect } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import WebApp from "@twa-dev/sdk";
import { authTelegram } from "./api/client";
import { useAuth } from "./store";
import Boot    from "./pages/Boot";
import Home    from "./pages/Home";
import Study   from "./pages/Study";
import Catalog from "./pages/Catalog";
import Stats   from "./pages/Stats";
import NavBar  from "./components/NavBar";

export default function App() {
  const { token, setAuth, setReady } = useAuth();

  useEffect(() => {
    WebApp.ready();
    WebApp.expand();

    const initData = WebApp.initData;

    if (!initData) {
      // Dev fallback: mock auth
      console.warn("No Telegram initData — using dev mock");
      setAuth("dev-token", "dev-user", "Dev");
      setReady();
      return;
    }

    authTelegram(initData)
      .then(({ access_token, user }) => {
        setAuth(access_token, user.id, user.first_name);
      })
      .catch(console.error)
      .finally(setReady);
  }, []);

  if (!token) return <Boot />;

  return (
    <BrowserRouter>
      <div className="flex flex-col h-screen max-w-md mx-auto">
        <main className="flex-1 overflow-y-auto pb-16">
          <Routes>
            <Route path="/"         element={<Home />} />
            <Route path="/study"    element={<Study />} />
            <Route path="/catalog"  element={<Catalog />} />
            <Route path="/stats"    element={<Stats />} />
            <Route path="*"         element={<Navigate to="/" replace />} />
          </Routes>
        </main>
        <NavBar />
      </div>
    </BrowserRouter>
  );
}
