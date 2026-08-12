import { useMemo } from "react";
import { statsForChart } from "../lib/stats";
import type { ChartDataPoint } from "../lib/ChartData";
import { Bar } from "@/components/Chart";

export interface StatsProps {
  data: ChartDataPoint[];
  entry: number;
  exit: number;
  holdDays: number;
}

export const Stats: React.FC<StatsProps> = ({ data, entry, exit, holdDays }) => {
  const [selectedStat, setSelectedStat] = useState("all");
  const [showChart, setShowChart] = useState(false);

  const filteredData = useMemo(() => {
    if (selectedStat === "all") return data;
    return data.filter((d) => d.relativeStrength > 0);
  }, [data, selectedStat]);

  const stats = useMemo(() => {
    return statsForChart(data);
  }, [data]);

  return (
    <div className="card p-4 rounded-xl border border-slate-700">
      <h4 className="text-lg font-semibold text-slate-100 mb-4">
        Market Statistics
      </h4>

      {/* Key Metrics */}
      <div className="grid grid-cols-2 gap-4 mb-4">
        <div className="text-center p-3 bg-slate-900 rounded-lg">
          <p className="text-xs text-slate-400">Entry</p>
          <p className="text-xl font-bold text-emerald-400">{entry.toFixed(2)}</p>
        </div>
        <div className="text-center p-3 bg-slate-900 rounded-lg">
          <p className="text-xs text-slate-400">Exit</p>
          <p className="text-xl font-bold text-amber-400">{exit.toFixed(2)}</p>
        </div>
        <div className="text-center p-3 bg-slate-900 rounded-lg">
          <p className="text-xs text-slate-400">Hold Days</p>
          <p className="text-xl font-bold text-blue-400">{holdDays.toFixed(0)}</p>
        </div>
        <div className="text-center p-3 bg-slate-900 rounded-lg">
          <p className="text-xs text-slate-400">RSI</p>
          <p className="text-xl font-bold text-red-400">
            {stats.relativeStrength.toFixed(1)}
          </p>
        </div>
      </div>

      {/* Toggle Chart */}
      <div className="flex gap-2 mb-4">
        {["all", "strong", "weak"].map((stat) => (
          <button
            key={stat}
            onClick={() => setSelectedStat(stat)}
            className={`px-3 py-1 rounded text-sm font-medium ${
              selectedStat === stat
                ? "bg-slate-700 text-white"
                : "bg-slate-800 text-slate-400"
            }`}
          >
            {stat === "all" ? "All" : stat.charAt(0).toUpperCase() + stat.slice(1)}
          </button>
        ))}
      </div>

      {/* Chart */}
      {showChart && (
        <div className="mt-4">
          <Chart data={filteredData} />
        </div>
      )}
    </div>
  );
};

export default Stats;