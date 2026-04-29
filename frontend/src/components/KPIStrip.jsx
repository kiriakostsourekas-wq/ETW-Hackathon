import { Line, LineChart, ResponsiveContainer, Tooltip } from "recharts";

const loadingKpis = [
  { label: "Net Revenue", value: "Loading", badge: "API", detail: "Optimizer running", sparkline: [0, 1, 0, 1] },
  { label: "Captured Spread", value: "Loading", badge: "DAM", detail: "Waiting for price data", sparkline: [0, 1, 0, 1] },
  { label: "Energy Shifted", value: "Loading", badge: "BESS", detail: "Waiting for schedule", sparkline: [0, 1, 0, 1] },
  { label: "Equivalent Cycles", value: "Loading", badge: "Constraint", detail: "Waiting for optimizer", sparkline: [0, 1, 0, 1], active: true },
];

function Sparkline({ values }) {
  const data = values.map((value, index) => ({ index, value }));

  return (
    <div className="h-14 w-40">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 4, right: 4, left: 4, bottom: 4 }}>
          <Tooltip
            contentStyle={{ background: "#111111", border: "1px solid #d4f700", borderRadius: 8, color: "#ffffff" }}
            formatter={(value) => [Number(value).toLocaleString(), "Value"]}
            labelFormatter={() => "Hourly value"}
          />
          <Line type="monotone" dataKey="value" stroke="#e9ef5a" strokeWidth={2.4} dot={false} activeDot={{ r: 3, fill: "#d4f700" }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function KPIItem({ item }) {
  return (
    <article className={`metric-card relative grid h-full grid-cols-[1fr_168px] items-center overflow-visible px-4 ${item.active ? "border-b-[7px] border-dashboard-accent" : ""}`}>
      {item.active && <div className="absolute bottom-[-15px] left-1/2 h-0 w-0 -translate-x-1/2 border-l-[10px] border-r-[10px] border-t-[10px] border-l-transparent border-r-transparent border-t-dashboard-accent" />}
      <div>
        <div className="mb-2 flex items-center gap-2">
          <span className="text-base font-extrabold">{item.label}</span>
          <span className="rounded bg-[#008d81] px-2 py-0.5 text-[10px] font-extrabold text-white">{item.badge}</span>
        </div>
        <div className="text-2xl font-black tracking-normal text-white">{item.value}</div>
        <div className="mt-4 flex items-center gap-2 text-xs font-semibold text-white/65">
          <span className="h-2 w-2 rounded-full bg-dashboard-accent" />
          <span>{item.detail}</span>
        </div>
      </div>
      <div className="flex flex-col items-end">
        <Sparkline values={item.sparkline ?? []} />
        <div className="mt-[-4px] flex w-40 justify-between text-[10px] font-semibold text-dashboard-muted">
          <span>00:00</span>
          <span>23:45</span>
        </div>
      </div>
    </article>
  );
}

export default function KPIStrip({ dashboard, loading }) {
  const kpis = loading || !dashboard?.kpis ? loadingKpis : dashboard.kpis;

  return (
    <section className="grid min-h-0 grid-cols-4 gap-4">
      {kpis.map((item) => (
        <KPIItem key={item.label} item={item} />
      ))}
    </section>
  );
}
