import { useState } from "react";
import TopNav from "./components/TopNav.jsx";
import HeroStatus from "./components/HeroStatus.jsx";
import KPIStrip from "./components/KPIStrip.jsx";
import OperationsPanel from "./components/OperationsPanel.jsx";
import ReportsPanel from "./components/ReportsPanel.jsx";
import { fetchDashboardData } from "./api.js";
import { useEffect } from "react";

export default function App() {
  const [view, setView] = useState("operations");
  const [dashboard, setDashboard] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function loadDashboard() {
    setLoading(true);
    setError("");
    try {
      setDashboard(await fetchDashboardData());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Dashboard API failed");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadDashboard();
  }, []);

  return (
    <main className="h-screen w-screen overflow-hidden bg-[#68bff5] p-4 text-white">
      <div className="grid h-full overflow-hidden rounded-[18px] bg-dashboard-bg shadow-[0_16px_35px_rgba(0,0,0,0.45)]">
        <div className="grid min-h-0 grid-rows-[52px_minmax(0,1fr)]">
          <TopNav
            activeView={view}
            dashboard={dashboard}
            loading={loading}
            onRefresh={loadDashboard}
            onViewChange={setView}
          />
          <section className="grid min-h-0 grid-rows-[132px_90px_minmax(0,1fr)] gap-4 p-4">
            <HeroStatus dashboard={dashboard} error={error} loading={loading} onRefresh={loadDashboard} />
            <KPIStrip dashboard={dashboard} loading={loading} />
            {view === "reports" ? (
              <ReportsPanel dashboard={dashboard} loading={loading} />
            ) : (
              <OperationsPanel dashboard={dashboard} loading={loading} />
            )}
          </section>
        </div>
      </div>
    </main>
  );
}
