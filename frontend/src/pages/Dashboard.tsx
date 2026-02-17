import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { listDocuments } from "../api/documents";
import { getPipelineStats } from "../api/stats";
import { useAuth } from "../context/AuthContext";
import { publishToast } from "../lib/toastBus";
import client from "../api/client";
import LoadingSpinner from "../components/LoadingSpinner";
import type { PipelineStats } from "../types";

export default function Dashboard() {
  const { user, isAdmin } = useAuth();
  const navigate = useNavigate();
  const [stats, setStats] = useState<PipelineStats | null>(null);
  const [docCounts, setDocCounts] = useState({ total: 0, needsReview: 0, approved: 0 });
  const [loading, setLoading] = useState(true);
  const [purging, setPurging] = useState(false);
  const [resetting, setResetting] = useState(false);

  async function load() {
    try {
      const [s, all] = await Promise.all([
        getPipelineStats(),
        listDocuments({ limit: 1 }),
      ]);
      setStats(s);
      setDocCounts({
        total: all?.total ?? 0,
        needsReview: 0,
        approved: all?.total ?? 0,
      });
    } catch (err) {
      console.error("Dashboard load error:", err);
    }
    setLoading(false);
  }

  useEffect(() => { load(); }, []);

  const handlePurge = async () => {
    if (!confirm("Remove document records whose PDF files are missing from disk?")) return;
    setPurging(true);
    try {
      const res = await client.delete("/api/system/purge-orphans");
      publishToast({ message: res.data.message, type: "success" });
      await load();
    } catch { publishToast({ message: "Purge failed", type: "error" }); }
    setPurging(false);
  };

  const handleReset = async () => {
    if (!confirm("⚠️ DELETE all crawl sessions, documents, and files?")) return;
    if (!confirm("Are you absolutely sure? This cannot be undone.")) return;
    setResetting(true);
    try {
      const res = await client.delete("/api/system/reset");
      publishToast({ message: res.data.message, type: "success" });
      await load();
    } catch { publishToast({ message: "Reset failed", type: "error" }); }
    setResetting(false);
  };

  if (loading) return <LoadingSpinner />;

  const stageValues = stats?.stages ? Object.values(stats.stages) : [];
  const maxStageValue = stageValues.length > 0 ? Math.max(...stageValues, 1) : 1;

  const cards = [
    { label: "Total Documents", value: docCounts.total, color: "text-primary-600", action: () => navigate("/library") },
    { label: "Needs Review", value: docCounts.needsReview, color: "text-amber-600", action: () => navigate("/review") },
    { label: "Approved", value: docCounts.approved, color: "text-emerald-600", action: () => navigate("/library") },
    { label: "Pipeline Stages", value: Object.keys(stats?.stages || {}).length, color: "text-violet-600", action: () => navigate("/funnel") },
  ];

  return (
    <div>
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-gray-900">Dashboard</h1>
          <p className="mt-1 text-sm text-gray-500">Welcome back, {user?.name ?? "User"}</p>
        </div>
        <button
          onClick={() => navigate("/crawl")}
          className="rounded-lg bg-primary-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-primary-700"
        >
          Open Crawl Manager
        </button>
      </div>

      {/* Stat Cards */}
      <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
        {cards.map((card) => (
          <button
            key={card.label}
            onClick={card.action}
            className="rounded-xl border border-gray-200 bg-white p-6 text-left shadow-sm transition-all hover:shadow-md"
          >
            <p className="text-sm font-medium text-gray-500">{card.label}</p>
            <p className={`mt-2 text-3xl font-bold ${card.color}`}>{card.value}</p>
          </button>
        ))}
      </div>

      {/* Pipeline Throughput */}
      {stats && Object.keys(stats.stages).length > 0 ? (
        <div className="mt-8 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="mb-4 text-lg font-semibold text-gray-900">Pipeline Throughput</h2>
          <div className="space-y-3">
            {Object.entries(stats.stages).map(([stage, count]) => (
              <div key={stage} className="flex items-center gap-4">
                <span className="w-36 text-sm text-gray-600 capitalize">{stage.replace(/_/g, " ")}</span>
                <div className="flex-1">
                  <div className="h-6 overflow-hidden rounded-full bg-gray-100">
                    <div
                      className="h-full rounded-full bg-primary-500 transition-all duration-500"
                      style={{ width: `${Math.min(100, (count / maxStageValue) * 100)}%` }}
                    />
                  </div>
                </div>
                <span className="w-12 text-right text-sm font-medium text-gray-700">{count}</span>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="mt-8 rounded-xl border border-gray-200 bg-white p-6 shadow-sm text-center">
          <p className="text-gray-500">No pipeline data yet. Start a crawl to see throughput.</p>
        </div>
      )}

      {/* Admin Tools */}
      {isAdmin && (
        <div className="mt-8 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="mb-4 text-lg font-semibold text-gray-900">Admin Tools</h2>
          <div className="flex flex-wrap gap-3">
            <button onClick={handlePurge} disabled={purging}
              className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-amber-600 disabled:opacity-50">
              {purging ? "Purging..." : "Purge Stale Records"}
            </button>
            <button onClick={handleReset} disabled={resetting}
              className="rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-red-700 disabled:opacity-50">
              {resetting ? "Resetting..." : "Full System Reset"}
            </button>
          </div>
          <p className="mt-2 text-xs text-gray-500">Purge removes stale DB records with missing files. Full Reset deletes everything.</p>
        </div>
      )}
    </div>
  );
}
