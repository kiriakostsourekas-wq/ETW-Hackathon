function LogoMark() {
  return (
    <div className="flex items-center gap-2">
      <div className="flex h-5 w-9 items-center rounded-full border border-white/70 bg-[#222222] p-0.5 shadow-[0_0_8px_rgba(212,247,0,0.25)]">
        <span className="h-3.5 w-3.5 rounded-full bg-dashboard-accent" />
      </div>
      <span className="text-base font-extrabold tracking-normal text-dashboard-accent">Logo</span>
    </div>
  );
}

function SelectorPill({ label, wide = false }) {
  return (
    <button
      type="button"
      className={`flex h-8 items-center justify-between rounded-full bg-black px-4 text-xs font-extrabold text-white shadow-[0_0_0_1px_#2a2a2a] ${wide ? "w-44" : "w-32"}`}
    >
      <span className="truncate">{label}</span>
      <svg width="10" height="10" viewBox="0 0 12 12" fill="none" aria-hidden="true">
        <path d="M3 4.5 6 7.5l3-3" stroke="#888888" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </button>
  );
}

function IconButton({ children, active = false, label, onClick }) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      onClick={onClick}
      className={`flex h-9 w-9 items-center justify-center rounded-full transition ${active ? "bg-white/10 text-dashboard-accent" : "text-white/80 hover:bg-white/5"}`}
    >
      {children}
    </button>
  );
}

function DocumentIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="6" y="3.5" width="12" height="17" rx="1.5" stroke="currentColor" strokeWidth="2" />
      <path d="M9 8h6M9 12h6M9 16h4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function BellIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M18 9.8a6 6 0 0 0-12 0c0 6-2 6.8-2 6.8h16s-2-.8-2-6.8Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M9.7 20a2.5 2.5 0 0 0 4.6 0" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function UserIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="8" r="3.4" stroke="currentColor" strokeWidth="1.8" />
      <path d="M5.8 20c.7-3.1 3-5 6.2-5s5.5 1.9 6.2 5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

function MenuIcon() {
  return (
    <svg width="19" height="19" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M5 7h14M5 12h14M5 17h14" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" />
    </svg>
  );
}

function RefreshIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M20 12a8 8 0 1 1-2.4-5.7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <path d="M20 4v6h-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default function TopNav({ activeView, dashboard, loading, onRefresh, onViewChange }) {
  const asset = dashboard?.asset;
  const dataQuality = dashboard?.data_quality ?? "waiting for backend";

  return (
    <header className="grid h-[52px] grid-cols-[1fr_auto_1fr] items-center border-b border-dashboard-border bg-[#202124] px-5">
      <LogoMark />

      <div className="flex items-center gap-4">
        <SelectorPill label="GREECE" />
        <SelectorPill label={asset?.region ?? "THESSALY BESS"} wide />
        <SelectorPill label={asset ? `${asset.params.power_mw.toFixed(0)}MW` : "METLEN_330"} />
      </div>

      <div className="flex items-center justify-end gap-3">
        <span className={`mr-2 rounded-full px-3 py-1 text-[10px] font-extrabold uppercase ${dashboard?.metrics?.public_price_data ? "bg-dashboard-accent/15 text-dashboard-accent" : "bg-white/10 text-white/55"}`}>
          {loading ? "Loading" : dataQuality}
        </span>
        <IconButton label="Reports" active={activeView === "reports"} onClick={() => onViewChange("reports")}>
          <DocumentIcon />
        </IconButton>
        <IconButton label="Alerts">
          <BellIcon />
        </IconButton>
        <IconButton label="Operator">
          <UserIcon />
        </IconButton>
        <IconButton label="Refresh data" onClick={onRefresh}>
          <RefreshIcon />
        </IconButton>
        <IconButton label="Operations" active={activeView === "operations"} onClick={() => onViewChange("operations")}>
          <MenuIcon />
        </IconButton>
      </div>
    </header>
  );
}
