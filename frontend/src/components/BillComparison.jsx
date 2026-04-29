import { useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const billBySector = [
  { month: "Jan", savings: 921000, comparison: 612000, withoutSavings: 664000, withSavings: 529000, y2023: null, y2024: 196000 },
  { month: "Feb", savings: 618000, comparison: 474000, withoutSavings: 586000, withSavings: 481000, y2023: null, y2024: 350000 },
  { month: "Mar", savings: 245000, comparison: 336000, withoutSavings: 612000, withSavings: 543000, y2023: null, y2024: 62000 },
  { month: "Apr", savings: 348000, comparison: 332000, withoutSavings: 638000, withSavings: 548000, y2023: null, y2024: 642000 },
  { month: "May", savings: 806000, comparison: 528000, withoutSavings: 581000, withSavings: 530000, y2023: null, y2024: 575000 },
  { month: "Jun", savings: 530000, comparison: 421000, withoutSavings: 432000, withSavings: 391000, y2023: 448000, y2024: 640000 },
  { month: "Jul", savings: 184000, comparison: 282000, withoutSavings: 474000, withSavings: 456000, y2023: 463000, y2024: 532000 },
  { month: "Aug", savings: 284000, comparison: 361000, withoutSavings: 575000, withSavings: 523000, y2023: 305000, y2024: 623000 },
  { month: "Sep", savings: 672000, comparison: 472000, withoutSavings: 601000, withSavings: 543000, y2023: 584000, y2024: 503000 },
  { month: "Oct", savings: 379000, comparison: 351000, withoutSavings: 510000, withSavings: 453000, y2023: 63000, y2024: 529000 },
  { month: "Nov", savings: 533000, comparison: 418000, withoutSavings: 572000, withSavings: 499000, y2023: 286000, y2024: 442000 },
  { month: "Dec", savings: 1082368, comparison: 689000, withoutSavings: 612711, withSavings: 504743, y2023: 365000, y2024: 198000 },
];

const comparisonData = [
  { month: "Jan", savings: 730000, comparison: 454000, withoutSavings: 590000, withSavings: 496000, y2023: 310000, y2024: 238000 },
  { month: "Feb", savings: 470000, comparison: 362000, withoutSavings: 548000, withSavings: 468000, y2023: 380000, y2024: 398000 },
  { month: "Mar", savings: 515000, comparison: 426000, withoutSavings: 575000, withSavings: 499000, y2023: 295000, y2024: 265000 },
  { month: "Apr", savings: 602000, comparison: 388000, withoutSavings: 604000, withSavings: 516000, y2023: 430000, y2024: 590000 },
  { month: "May", savings: 865000, comparison: 544000, withoutSavings: 652000, withSavings: 541000, y2023: 510000, y2024: 641000 },
  { month: "Jun", savings: 690000, comparison: 521000, withoutSavings: 602000, withSavings: 482000, y2023: 486000, y2024: 552000 },
  { month: "Jul", savings: 340000, comparison: 296000, withoutSavings: 544000, withSavings: 472000, y2023: 410000, y2024: 606000 },
  { month: "Aug", savings: 568000, comparison: 402000, withoutSavings: 618000, withSavings: 534000, y2023: 332000, y2024: 476000 },
  { month: "Sep", savings: 770000, comparison: 532000, withoutSavings: 680000, withSavings: 561000, y2023: 548000, y2024: 665000 },
  { month: "Oct", savings: 438000, comparison: 365000, withoutSavings: 528000, withSavings: 462000, y2023: 222000, y2024: 512000 },
  { month: "Nov", savings: 632000, comparison: 478000, withoutSavings: 602000, withSavings: 500000, y2023: 300000, y2024: 457000 },
  { month: "Dec", savings: 956000, comparison: 644000, withoutSavings: 618000, withSavings: 509000, y2023: 392000, y2024: 226000 },
];

const metrics = [
  { label: "YTD Savings", unit: "$MX", value: "25,211,742,190", badge: "YTD 2024", active: true },
  { label: "Bill w/Out Savings", unit: "$MX", value: "6,127,111", badge: "Dec 2024" },
  { label: "Bill w/ Savings", unit: "$MX", value: "5,044,743", badge: "Dec 2024" },
  { label: "Total Savings", unit: "$MX", value: "1,082,368", badge: "Dec 2024" },
  { label: "Savings %", unit: "", value: "17.7%", badge: "Dec 2024" },
];

function PesoTick(value) {
  return `$MX ${Number(value).toLocaleString()}`;
}

function DashboardTooltip({ active, payload, label }) {
  if (!active || !payload?.length) {
    return null;
  }

  return (
    <div className="rounded-lg border border-dashboard-accent bg-[#111111] px-3 py-2 text-xs shadow-[0_0_18px_rgba(212,247,0,0.16)]">
      <div className="mb-1 font-extrabold text-white">{label}</div>
      {payload.map((entry) => (
        <div key={entry.dataKey} className="flex items-center gap-2 text-dashboard-muted">
          <span className="h-2 w-2 rounded-full" style={{ background: entry.color }} />
          <span>{entry.name}:</span>
          <span className="font-bold text-white">{PesoTick(entry.value)}</span>
        </div>
      ))}
    </div>
  );
}

function Badge({ children }) {
  return <span className="rounded bg-dashboard-accent/15 px-1.5 py-0.5 text-[10px] font-extrabold text-dashboard-accent">{children}</span>;
}

function CalendarIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="4" y="5" width="16" height="15" rx="2" stroke="#d4f700" strokeWidth="2" />
      <path d="M8 3v4M16 3v4M4 10h16" stroke="#d4f700" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function RefreshIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M20 12a8 8 0 1 1-2.4-5.7" stroke="#bbbbbb" strokeWidth="2" strokeLinecap="round" />
      <path d="M20 4v6h-6" stroke="#bbbbbb" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function SearchIcon() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="11" cy="11" r="6" stroke="#888888" strokeWidth="2.4" />
      <path d="m16 16 4 4" stroke="#888888" strokeWidth="2.4" strokeLinecap="round" />
    </svg>
  );
}

function Tabs({ activeTab, onChange }) {
  return (
    <div className="flex h-8 rounded-lg bg-black p-0.5 shadow-[0_0_0_1px_#2a2a2a]">
      {["Bill by Sector", "Comparison"].map((tab) => (
        <button
          type="button"
          key={tab}
          onClick={() => onChange(tab)}
          className={`h-7 rounded-md px-7 text-xs font-bold transition ${
            activeTab === tab ? "bg-dashboard-accent/45 text-dashboard-accent shadow-[inset_0_0_0_1px_rgba(212,247,0,0.25)]" : "text-white"
          }`}
        >
          {tab}
        </button>
      ))}
    </div>
  );
}

function PeriodSearch() {
  return (
    <div className="flex items-center gap-4">
      <div className="flex h-9 w-[330px] items-center gap-2 rounded-lg bg-black px-3 shadow-[0_0_0_1px_#2a2a2a]">
        <SearchIcon />
        <span className="flex-1 text-xs font-bold text-white">December 2024</span>
        <span className="text-[10px] font-extrabold text-dashboard-accent">Billing Cycle</span>
        <CalendarIcon />
      </div>
      <RefreshIcon />
    </div>
  );
}

function SummaryCard({ item }) {
  return (
    <article className={`metric-card relative flex h-full flex-col justify-center px-4 ${item.active ? "shadow-active" : ""}`}>
      <div className="absolute right-3 top-3">
        <Badge>{item.badge}</Badge>
      </div>
      <div className="text-sm font-semibold text-white/75">{item.label}</div>
      {item.unit ? <div className="mt-2 text-[10px] font-bold text-dashboard-muted">{item.unit}</div> : <div className="mt-2 h-[14px]" />}
      <div className="mt-[-3px] text-2xl font-black tracking-normal text-white">{item.value}</div>
    </article>
  );
}

function MonthlySavingsChart({ data }) {
  const chartData = data.map((item) => ({ ...item, comparison: Math.min(item.comparison, 1082368), savings: Math.min(item.savings, 1082368) }));

  return (
    <article className="dashboard-card min-h-0 p-4">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-bold text-white/85">Monthly Savings</h2>
        <Badge>YTD 2024</Badge>
      </div>
      <div className="h-[calc(100%-28px)] min-h-0">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} layout="vertical" margin={{ top: 4, right: 6, bottom: 18, left: 0 }} barCategoryGap={6}>
            <XAxis
              type="number"
              domain={[0, 1082368]}
              ticks={[0, 1082368]}
              tickFormatter={PesoTick}
              axisLine={false}
              tickLine={false}
              tick={{ fill: "#888888", fontSize: 10, fontWeight: 700 }}
            />
            <YAxis type="category" dataKey="month" axisLine={false} tickLine={false} width={28} tick={{ fill: "#cfcfcf", fontSize: 11, fontWeight: 700 }} />
            <Tooltip content={<DashboardTooltip />} />
            <Bar name="Savings" dataKey="savings" fill="#d4f700" radius={[3, 3, 3, 3]} barSize={6} />
            <Bar name="Comparison" dataKey="comparison" fill="#4fc3f7" radius={[3, 3, 3, 3]} barSize={6} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </article>
  );
}

function BillComparisonChart({ data }) {
  return (
    <article className="dashboard-card min-h-0 p-4">
      <div className="mb-2 flex items-center justify-between gap-3">
        <h2 className="text-sm font-bold text-white/85">Bill Comparison</h2>
        <div className="flex flex-1 items-center justify-end gap-4 text-xs font-bold text-white/80">
          <span className="inline-flex items-center gap-2"><span className="h-3 w-4 rounded-sm bg-[#555555]" />Bill w/Out Savings</span>
          <span className="inline-flex items-center gap-2"><span className="h-3 w-4 rounded-sm bg-dashboard-accent" />Bill w/ Savings</span>
          <Badge>YTD 2024</Badge>
        </div>
      </div>
      <div className="h-[calc(100%-28px)] min-h-0">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 4, bottom: 0, left: 6 }} barGap={4}>
            <CartesianGrid stroke="#343434" vertical={false} />
            <XAxis dataKey="month" axisLine={false} tickLine={false} tick={{ fill: "#cfcfcf", fontSize: 11, fontWeight: 700 }} />
            <YAxis
              axisLine={false}
              tickLine={false}
              width={64}
              domain={[0, 700000]}
              ticks={[0, 100000, 200000, 300000, 400000, 500000, 600000, 700000]}
              tickFormatter={PesoTick}
              tick={{ fill: "#cfcfcf", fontSize: 10, fontWeight: 700 }}
            />
            <Tooltip content={<DashboardTooltip />} />
            <Bar name="Bill w/Out Savings" dataKey="withoutSavings" fill="#555555" radius={[4, 4, 0, 0]} barSize={12} />
            <Bar name="Bill w/ Savings" dataKey="withSavings" fill="#d4f700" radius={[4, 4, 0, 0]} barSize={12} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </article>
  );
}

function SavingsComparisonChart({ data }) {
  const lineData = data.map((item) => ({ ...item, y2023: item.y2023 ?? undefined }));

  return (
    <article className="dashboard-card min-h-0 p-4">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-bold text-white/85">Savings Comparison</h2>
        <div className="flex items-center gap-4 text-xs font-bold">
          <span className="inline-flex items-center gap-2 text-white/80"><span className="h-2 w-4 rounded-full bg-dashboard-blue" />2023</span>
          <span className="inline-flex items-center gap-2 text-white/80"><span className="h-2 w-4 rounded-full bg-dashboard-accent" />2024</span>
          <Badge>YTD 2024</Badge>
        </div>
      </div>
      <div className="h-[calc(100%-28px)] min-h-0">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={lineData} margin={{ top: 8, right: 8, bottom: 0, left: 6 }}>
            <CartesianGrid stroke="#343434" vertical={false} />
            <XAxis dataKey="month" axisLine={false} tickLine={false} tick={{ fill: "#cfcfcf", fontSize: 11, fontWeight: 700 }} />
            <YAxis
              axisLine={false}
              tickLine={false}
              width={64}
              domain={[0, 700000]}
              ticks={[0, 100000, 200000, 300000, 400000, 500000, 600000, 700000]}
              tickFormatter={PesoTick}
              tick={{ fill: "#cfcfcf", fontSize: 10, fontWeight: 700 }}
            />
            <Tooltip content={<DashboardTooltip />} />
            <Line name="2023" type="monotone" dataKey="y2023" stroke="#4fc3f7" strokeWidth={2.2} dot={{ r: 3, fill: "#4fc3f7" }} connectNulls={false} />
            <Line name="2024" type="monotone" dataKey="y2024" stroke="#d4f700" strokeWidth={2.2} dot={{ r: 3, fill: "#d4f700" }} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </article>
  );
}

export default function BillComparison() {
  const [activeTab, setActiveTab] = useState("Comparison");
  const data = useMemo(() => (activeTab === "Comparison" ? comparisonData : billBySector), [activeTab]);

  return (
    <section className="dashboard-card grid min-h-0 grid-rows-[44px_74px_minmax(0,1fr)] gap-4 p-4">
      <div className="flex items-center justify-between">
        <Tabs activeTab={activeTab} onChange={setActiveTab} />
        <PeriodSearch />
      </div>

      <div className="grid min-h-0 grid-cols-5 gap-4">
        {metrics.map((item) => (
          <SummaryCard key={item.label} item={item} />
        ))}
      </div>

      <div className="grid min-h-0 grid-cols-[0.82fr_1.65fr_1.65fr] gap-4">
        <MonthlySavingsChart data={data} />
        <BillComparisonChart data={data} />
        <SavingsComparisonChart data={data} />
      </div>
    </section>
  );
}
