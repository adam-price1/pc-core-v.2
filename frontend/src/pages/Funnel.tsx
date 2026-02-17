import { useEffect, useState } from "react";
import { getPipelineStats } from "../api/stats";
import LoadingSpinner from "../components/LoadingSpinner";
import type { PipelineStats } from "../types";

const STAGE_COLORS = [
  "bg-blue-500", "bg-blue-400", "bg-cyan-500", "bg-teal-500",
  "bg-emerald-500", "bg-amber-500", "bg-green-500", "bg-green-600", "bg-gray-400",
];

export default function Funnel() {
  const [stats, setStats] = useState<PipelineStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getPipelineStats().then(setStats).catch(() => {}).finally(() => setLoading(false));
  }, []);

  if (loading) return <LoadingSpinner />;

  const stages = stats?.stages ? Object.entries(stats.stages) : [];
  const funnelRates = stats?.funnel_rates ?? {};

  if (stages.length === 0) {
    return (
      <div>
        <div className="mb-8">
          <h1 className="text-2xl font-bold tracking-tight text-gray-900">Pipeline Funnel</h1>
        </div>
        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm text-center">
          <p className="text-gray-500">No pipeline data yet. Start a crawl to see the funnel.</p>
        </div>
      </div>
    );
  }

  const maxVal = Math.max(...stages.map(([, c]) => c), 1);

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold tracking-tight text-gray-900">Pipeline Funnel</h1>
        <p className="mt-1 text-sm text-gray-500">{stages.length} stages</p>
      </div>

      <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <div className="space-y-4">
          {stages.map(([stage, count], i) => {
            const pct = (count / maxVal) * 100;
            return (
              <div key={stage}>
                <div className="mb-1.5 flex items-center justify-between">
                  <span className="text-sm font-medium text-gray-700 capitalize">{stage.replace(/_/g, " ")}</span>
                  <span className="text-sm font-semibold text-gray-900">{count}</span>
                </div>
                <div className="h-8 overflow-hidden rounded-lg bg-gray-100">
                  <div
                    className={`h-full rounded-lg ${STAGE_COLORS[i % STAGE_COLORS.length]} transition-all duration-700`}
                    style={{ width: `${Math.max(2, pct)}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {Object.keys(funnelRates).length > 0 && (
        <div className="mt-6 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="mb-4 text-lg font-semibold text-gray-900">Conversion Rates</h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {Object.entries(funnelRates).map(([key, rate]) => (
              <div key={key} className="rounded-lg border border-gray-100 bg-gray-50 p-3">
                <p className="text-xs text-gray-500 capitalize">{key.replace(/_/g, " ")}</p>
                <p className={`mt-1 text-lg font-bold ${(rate as number) >= 80 ? "text-green-600" : (rate as number) >= 50 ? "text-amber-600" : "text-red-600"}`}>
                  {(rate as number).toFixed(1)}%
                </p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
