import { useEffect, useState } from "react";

function SunIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="4" stroke="#d4f700" strokeWidth="2" />
      <path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M19.8 4.2l-2.1 2.1M6.3 17.7l-2.1 2.1" stroke="#d4f700" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function LightningIcon({ color = "#d4f700", size = 18 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M13.5 2 5 13h6l-1 9 8.5-12H13l.5-8Z" fill={color} />
    </svg>
  );
}

function HeartIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M12 20s-7-4.2-7-10.1C5 6.7 7 5 9.4 5c1.4 0 2.3.7 2.6 1.2.3-.5 1.2-1.2 2.6-1.2C17 5 19 6.7 19 9.9 19 15.8 12 20 12 20Z" fill="#0f0f0f" />
      <path d="M5 12h4l1.2-2.2 2.3 5.2 1.5-3h5" stroke="#0f0f0f" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function CloudRainIcon() {
  return (
    <svg width="58" height="58" viewBox="0 0 80 80" fill="none" aria-hidden="true">
      <path d="M24 46h33c8 0 14-5.9 14-13.2 0-7.4-6-13.1-13.7-13.1-2 0-3.8.4-5.4 1.1C48.9 14 42.3 10 34.8 10 24.2 10 16 18.2 16 28.2c0 .5 0 1 .1 1.5C10.2 31 6 35.8 6 41.8 6 48.6 11.5 54 18.5 54H24" stroke="#ffffff" strokeWidth="4" strokeLinecap="round" />
      <path d="M24 61l-4 7M39 58l-4 8M54 60l-4 7" stroke="#ffffff" strokeWidth="4" strokeLinecap="round" />
    </svg>
  );
}

function SiteInfoCard() {
  return (
    <article className="dashboard-card flex h-full flex-col justify-center border-l-4 border-dashboard-accent px-4">
      <h1 className="mb-4 text-lg font-extrabold text-dashboard-accent">Shopping Center City, USA</h1>
      <div className="flex items-center gap-2 text-sm font-semibold text-white/90">
        <SunIcon />
        <span>CFE Peak Shaving</span>
      </div>
      <div className="mt-2 flex items-center gap-2 text-sm font-semibold text-white/90">
        <LightningIcon />
        <span>1.7 MW / 3.5 MWh</span>
      </div>
    </article>
  );
}

function NodeIcon({ type }) {
  if (type === "solar") {
    return (
      <g>
        <rect x="-7" y="-5" width="14" height="10" rx="1" stroke="#bfbfbf" strokeWidth="1.3" fill="#2a2a2a" />
        <path d="M-3 -5v10M2 -5v10M-7 -1h14M-7 3h14" stroke="#bfbfbf" strokeWidth="0.8" />
      </g>
    );
  }

  if (type === "battery") {
    return (
      <g>
        <rect x="-7" y="-5" width="14" height="10" rx="2" stroke="#bfbfbf" strokeWidth="1.3" fill="#2a2a2a" />
        <rect x="7" y="-2" width="2" height="4" rx="1" fill="#bfbfbf" />
        <path d="M-2 -1h4M0 -3v4" stroke="#bfbfbf" strokeWidth="1.2" strokeLinecap="round" />
      </g>
    );
  }

  if (type === "building") {
    return (
      <g>
        <rect x="-8" y="-8" width="16" height="16" rx="1.5" stroke="#bfbfbf" strokeWidth="1.3" fill="#2a2a2a" />
        <path d="M-4 -4h2M2 -4h2M-4 0h2M2 0h2M-4 4h2M2 4h2" stroke="#bfbfbf" strokeWidth="1.1" strokeLinecap="round" />
      </g>
    );
  }

  return (
    <g>
      <path d="M0-10 8 10H-8L0-10Z" stroke="#d4f700" strokeWidth="1.5" fill="#2a2a2a" />
      <path d="M0-5v12M-5 7h10" stroke="#d4f700" strokeWidth="1.5" strokeLinecap="round" />
    </g>
  );
}

function FlowNode({ x, y, type, active = false }) {
  return (
    <g transform={`translate(${x} ${y})`}>
      <circle r="17" fill="#262626" stroke={active ? "#d4f700" : "#666666"} strokeWidth="2" />
      <NodeIcon type={type} />
    </g>
  );
}

function PowerFlow() {
  return (
    <article className="dashboard-card flex h-full items-center justify-center overflow-hidden px-3">
      <svg viewBox="0 0 300 118" className="h-full w-full" role="img" aria-label="Animated power flow from solar and storage to building and tower">
        <defs>
          <filter id="yellowGlow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="2.2" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        <path d="M56 36 C104 36 112 62 145 62" stroke="#d4f700" strokeWidth="2.2" fill="none" filter="url(#yellowGlow)" />
        <path d="M50 90 C99 90 111 62 145 62" stroke="#d4f700" strokeWidth="2.2" fill="none" filter="url(#yellowGlow)" opacity="0.85" />
        <path d="M145 62 C185 92 214 92 246 92" stroke="#d4f700" strokeWidth="2.2" fill="none" filter="url(#yellowGlow)" />
        <path d="M145 62 C183 36 214 36 246 36" stroke="#555555" strokeWidth="1.7" fill="none" />

        <circle className="flow-dot dot-path-solar flow-dot-a" r="3" fill="#d4f700" />
        <circle className="flow-dot dot-path-battery flow-dot-b" r="3" fill="#d4f700" />
        <circle className="flow-dot dot-path-tower flow-dot-c" r="3" fill="#d4f700" />

        <FlowNode x={56} y={36} type="battery" />
        <FlowNode x={50} y={90} type="solar" />
        <FlowNode x={145} y={62} type="building" active />
        <FlowNode x={246} y={36} type="building" />
        <FlowNode x={266} y={92} type="tower" active />

        <text x="86" y="28" fill="#ffffff" fontSize="11" fontWeight="700">3 kW</text>
        <text x="198" y="28" fill="#888888" fontSize="11" fontWeight="700">0.2 kW</text>
        <text x="88" y="82" fill="#ffffff" fontSize="11" fontWeight="700">0.1 kW</text>
        <text x="186" y="80" fill="#d4f700" fontSize="12" fontWeight="800">799 kW</text>
      </svg>
    </article>
  );
}

function BatteryWidget({ label, value, color, icon }) {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    const frame = requestAnimationFrame(() => setMounted(true));
    return () => cancelAnimationFrame(frame);
  }, []);

  return (
    <div className="flex flex-col items-center gap-2">
      <div className="relative h-[92px] w-[48px] rounded-lg border-2 border-[#777777] bg-[#101010] p-1 shadow-[inset_0_0_10px_rgba(255,255,255,0.06)]">
        <div className="absolute left-1/2 top-[-7px] h-1.5 w-5 -translate-x-1/2 rounded-t-md bg-[#777777]" />
        <div className="absolute left-0 top-2 z-10 w-full text-center text-[10px] font-extrabold text-white">{label}</div>
        <div className="absolute left-0 top-8 z-10 flex w-full justify-center">{icon}</div>
        <div className="absolute bottom-1 left-1 right-1 h-[60px] overflow-hidden rounded-md bg-[#262626]">
          <div className="battery-fill w-full rounded-md" style={{ height: mounted ? `${value}%` : "0%", background: color }} />
        </div>
        <div className="absolute bottom-3 left-0 z-10 w-full text-center text-[10px] font-extrabold text-[#111111]">{value}%</div>
      </div>
    </div>
  );
}

function BatteryStatus() {
  return (
    <article className="dashboard-card flex h-full items-center justify-center gap-5">
      <BatteryWidget label="SOC" value={30} color="#d4f700" icon={<LightningIcon color="#ffffff" size={16} />} />
      <BatteryWidget label="SOH" value={96} color="#4fc3f7" icon={<HeartIcon />} />
    </article>
  );
}

function WeatherMap() {
  return (
    <article className="grid h-full grid-cols-[0.95fr_1.35fr] gap-4">
      <div className="dashboard-card flex items-center justify-center gap-4">
        <CloudRainIcon />
        <div>
          <div className="text-sm font-bold text-white">Raining</div>
          <div className="text-2xl font-extrabold text-white">20 C</div>
        </div>
      </div>
      <div className="dashboard-card miami-map relative overflow-hidden">
        <div className="absolute inset-0 bg-black/18" />
        <div className="absolute left-3 top-3 rounded bg-black/60 px-2 py-1 text-[10px] font-semibold text-white/70">Miami-Dade Grid</div>
        <div className="absolute left-[56%] top-[38%] text-lg font-bold text-white">Miami</div>
        <div className="absolute left-[49%] top-[39%] h-11 w-8">
          <svg viewBox="0 0 40 54" aria-hidden="true">
            <path d="M20 52S4 32 4 18C4 8.6 11.1 2 20 2s16 6.6 16 16c0 14-16 34-16 34Z" fill="#d4f700" stroke="#0f0f0f" strokeWidth="3" />
            <circle cx="20" cy="18" r="7" fill="#0f0f0f" />
          </svg>
        </div>
      </div>
    </article>
  );
}

export default function StatusBar() {
  return (
    <section className="grid min-h-0 grid-cols-[1.05fr_1.35fr_0.65fr_1.35fr] gap-4">
      <SiteInfoCard />
      <PowerFlow />
      <BatteryStatus />
      <WeatherMap />
    </section>
  );
}
