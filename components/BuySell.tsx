import { format } from "date-fns";

export interface BuySellProps {
  entryZone: [number, number];
  sellZone: [number, number];
  holdDays: number;
  entryDayIdeal: Date;
  exitDayIdeal: Date;
  stopLoss: number;
  riskPct: number;
  rewardPct: number;
  riskReward: number;
  legRetPct: number;
  bestBuyHour?: string;
  bestSellHour?: string;
  TZ_LABEL?: string;
  inZone?: boolean;
}

export const BuySell: React.FC<BuySellProps> = ({
  entryZone,
  sellZone,
  holdDays,
  entryDayIdeal,
  exitDayIdeal,
  stopLoss,
  riskPct,
  rewardPct,
  riskReward,
  legRetPct,
  bestBuyHour,
  bestSellHour,
  TZ_LABEL,
  inZone,
}) => {
  const entryZoneNote = inZone
    ? "��✅ current price is in this zone"
    : "set a limit buy here for when it dips";

  const friendlyDate = (date: Date) =>
    date.toLocaleDateString(undefined, { weekday: "long", month: "short", day: "numeric" });

  return (
    <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
      {/* Buy Zone */}
      <div className="card bg-slate-800 p-4 rounded-xl border border-slate-700">
        <h4 className="text-lg font-semibold text-slate-100 mb-2">
          Next Buy Zone · Buy the Dip
        </h4>
        <div className="text-2xl font-bold text-emerald-400 mb-2">
          {format(entryZone[0], "###,##0.00")} – {format(entryZone[1], "###,##0.00")}
        </div>
        <div className="text-sm text-slate-400 mb-2">
          expect a dip here · <strong>{friendlyDate(entryDayIdeal)}</strong>{" "}
          {bestBuyHour ? ` around <strong>${bestBuyHour}</strong>` : ""}{" "}
          {TZ_LABEL && ` ${TZ_LABEL} · ${entryZoneNote}`}
        </div>
      </div>

      {/* Sell Zone */}
      <div className="card bg-slate-800 p-4 rounded-xl border border-slate-700">
        <h4 className="text-lg font-semibold text-slate-100 mb-2">
          Sell Target · Sell the Bounce
        </h4>
        <div className="text-2xl font-bold text-amber-400 mb-2">
          {format(sellZone[0], "###,##0.00")} – {format(sellZone[1], "###,##0.00")}
        </div>
        <div className="text-sm text-slate-400 mb-2">
          expect a bounce to here, then a pullback · take profit ~{" "}
          <strong>{friendlyDate(exitDayIdeal)}</strong>{" "}
          {bestSellHour ? ` around <strong>${bestSellHour}</strong>` : ""}{" "}
          {TZ_LABEL && ` ${TZ_LABEL} · ~${legRetPct.toFixed(0)}% from entry`}
        </div>
      </div>

      {/* Typical Hold */}
      <div className="card bg-slate-800 p-4 rounded-xl border border-slate-700">
        <h4 className="text-lg font-semibold text-slate-100 mb-2">
          Typical Hold
        </h4>
        <div className="text-3xl font-bold text-blue-400 mb-2">
          {holdDays.toFixed(0)} days
        </div>
        <div className="text-sm text-slate-400">
          in around <strong>{friendlyDate(entryDayIdeal)}</strong> → out around{" "}
          <strong>{friendlyDate(exitDayIdeal)}</strong>
        </div>
      </div>

      {/* Stop / Risk */}
      <div className="card bg-slate-800 p-4 rounded-xl border border-slate-700">
        <h4 className="text-lg font-semibold text-slate-100 mb-2">
          Stop / Risk
        </h4>
        <div className="text-2xl font-bold text-red-400 mb-2">
          {format(stopLoss, "###,##0.00")}
        </div>
        <div className="text-sm text-slate-400">
          risk {riskPct.toFixed(0)}% · reward {rewardPct.toFixed(0)}% ·{" "}
          1:{riskReward.toFixed(1)} RR
        </div>
      </div>
    </div>
  );
};

export default BuySell;