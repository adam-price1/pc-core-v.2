import { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { getCrawlStatus } from "../api/crawl";
import client from "../api/client";
import type { CrawlStatusResponse } from "../types";

interface LogEntry {
  ts: string;
  level: string;
  msg: string;
}

export default function Progress() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const crawlIdParam = searchParams.get("crawl_id");
  const [crawl, setCrawl] = useState<CrawlStatusResponse | null>(null);
  const [crawlId, setCrawlId] = useState<number | null>(crawlIdParam ? Number(crawlIdParam) : null);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [logIndex, setLogIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [showSeedUrls, setShowSeedUrls] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (crawlIdParam) {
      setCrawlId(Number(crawlIdParam));
      return;
    }
    client.get("/api/crawl/latest").then((res) => {
      const c = res.data?.crawl;
      if (c) setCrawlId(c.id);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, [crawlIdParam]);

  const fetchStatus = useCallback(async (id: number) => {
    try {
      const status = await getCrawlStatus(id);
      setCrawl(status);
      return status;
    } catch { return null; }
  }, []);

  const fetchLogs = useCallback(async (id: number, since: number) => {
    try {
      const res = await client.get(`/api/crawl/${id}/logs?since=${since}`);
      const data = res.data;
      if (data.entries?.length > 0) {
        setLogs((prev) => [...prev, ...data.entries]);
        setLogIndex(data.total);
        setTimeout(() => {
          if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
        }, 50);
      }
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    if (!crawlId) return;
    setLoading(true);
    fetchStatus(crawlId).then(() => setLoading(false));
    fetchLogs(crawlId, 0);

    if (pollRef.current) clearInterval(pollRef.current);
    let idx = 0;
    pollRef.current = setInterval(async () => {
      const s = await fetchStatus(crawlId);
      await fetchLogs(crawlId, idx);
      setLogIndex((prev) => { idx = prev; return prev; });
      if (s && (s.status === "completed" || s.status === "failed" || s.status === "stopped")) {
        await fetchLogs(crawlId, idx);
        if (pollRef.current) clearInterval(pollRef.current);
      }
    }, 2000);

    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [crawlId, fetchStatus, fetchLogs]);

  if (loading) {
    return (
      <div className="text-center py-20">
        <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-primary-500 border-r-transparent" />
        <p className="mt-4 text-gray-500">Loading crawl status...</p>
      </div>
    );
  }

  if (!crawlId || !crawl) {
    return (
      <div className="text-center py-20">
        <p className="text-gray-500 mb-4">No crawl found.</p>
        <button onClick={() => navigate("/crawl")}
          className="px-6 py-3 bg-primary-600 text-white rounded-lg font-semibold hover:bg-primary-700">
          Go to Crawl Manager
        </button>
      </div>
    );
  }

  const isRunning = crawl.status === "running";
  const isDone = crawl.status === "completed" || crawl.status === "failed";
  const seedUrlCount = crawl.seed_urls_crawled?.length ?? 0;
  const insurerNames = crawl.insurers_list ?? [];
  const pct = crawl.progress_pct ?? 0;

  return (
    <div>
      <div className="mb-6 flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 mb-1">
            Crawl #{crawl.id} {isRunning ? "in Progress" : isDone ? (crawl.status === "completed" ? "Complete" : "Failed") : ""}
          </h1>
          <p className="text-gray-600">
            {isRunning ? "Scanning websites for insurance policy documents..." :
             crawl.status === "completed" ? "Crawl finished successfully" :
             crawl.status === "failed" ? "Crawl encountered an error" : crawl.status}
          </p>
        </div>
        <div className="flex gap-3">
          {isDone && (
            <button onClick={() => navigate("/review")}
              className="px-5 py-2.5 bg-primary-600 text-white rounded-lg font-semibold hover:bg-primary-700">
              View Results
            </button>
          )}
          <button onClick={() => navigate("/crawl")}
            className="px-5 py-2.5 bg-gray-200 text-gray-700 rounded-lg font-semibold hover:bg-gray-300">
            Crawl Manager
          </button>
        </div>
      </div>

      {/* Progress Bar - Enhanced */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6">
        <div className="flex justify-between items-center mb-2">
          <div className="flex items-center gap-3">
            <span className="text-sm font-medium text-gray-700">
              {crawl.current_phase || "Progress"}
            </span>
            {crawl.phase_detail && (
              <span className="text-xs text-gray-500 bg-gray-100 rounded-full px-2.5 py-0.5">
                {crawl.phase_detail}
              </span>
            )}
          </div>
          <span className="text-lg font-bold text-primary-600">{pct}%</span>
        </div>
        <div className="w-full h-4 bg-gray-100 rounded-full overflow-hidden">
          {/* Two-phase bar: scanning (blue) 0-50%, downloading (green) 50-100% */}
          <div className="h-full flex">
            <div
              className={`h-full transition-all duration-700 ease-out ${
                crawl.status === "failed"
                  ? "bg-red-500"
                  : pct <= 50
                    ? "bg-gradient-to-r from-blue-400 to-blue-500"
                    : "bg-gradient-to-r from-blue-500 to-blue-500"
              }`}
              style={{ width: `${Math.min(pct, 50)}%` }}
            />
            {pct > 50 && (
              <div
                className="h-full bg-gradient-to-r from-emerald-400 to-emerald-500 transition-all duration-700 ease-out"
                style={{ width: `${pct - 50}%` }}
              />
            )}
          </div>
        </div>
        <div className="mt-2 flex items-center justify-between">
          <div className="flex items-center gap-4 text-xs text-gray-500">
            {isRunning && (
              <div className="flex items-center gap-1.5">
                <div className="h-2 w-2 rounded-full bg-green-500 animate-pulse" />
                <span>{pct < 50 ? "Scanning pages..." : "Downloading PDFs..."}</span>
              </div>
            )}
          </div>
          {pct <= 50 && pct > 0 && (
            <div className="flex gap-4 text-xs">
              <span className="text-blue-600 font-medium">Phase 1: Scanning</span>
              <span className="text-gray-400">Phase 2: Downloading</span>
            </div>
          )}
          {pct > 50 && pct < 100 && (
            <div className="flex gap-4 text-xs">
              <span className="text-blue-600 font-medium">Phase 1: Done</span>
              <span className="text-emerald-600 font-medium">Phase 2: Downloading</span>
            </div>
          )}
        </div>
      </div>

      {/* Insurers & Seed URLs Info */}
      {(insurerNames.length > 0 || seedUrlCount > 0) && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5 mb-6">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-semibold text-gray-700">Crawl Target</h3>
            <span className="text-xs text-gray-400">{crawl.country} · {seedUrlCount} seed URLs · {insurerNames.length} insurers</span>
          </div>
          {insurerNames.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mb-2">
              {insurerNames.map((name) => (
                <span key={name} className="rounded-full bg-primary-50 px-2.5 py-0.5 text-xs font-medium text-primary-700 border border-primary-200">
                  {name}
                </span>
              ))}
            </div>
          )}
          {seedUrlCount > 0 && (
            <div>
              <button onClick={() => setShowSeedUrls(!showSeedUrls)}
                className="text-xs font-medium text-primary-600 hover:text-primary-800">
                {showSeedUrls ? "▼ Hide" : "▶ Show"} {seedUrlCount} seed URLs
              </button>
              {showSeedUrls && (
                <div className="mt-2 rounded-lg border border-gray-200 bg-gray-50 p-3 max-h-40 overflow-y-auto">
                  {crawl.seed_urls_crawled?.map((url, i) => (
                    <div key={i} className="text-xs font-mono text-gray-600 py-0.5 truncate" title={url}>{url}</div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Stats Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        {[
          { label: "Pages Scanned", value: crawl.pages_scanned ?? 0, color: "text-blue-600", bg: "from-blue-50 to-blue-100" },
          { label: "PDFs Discovered", value: crawl.pdfs_found ?? 0, color: "text-purple-600", bg: "from-purple-50 to-purple-100" },
          { label: "PDFs Downloaded", value: crawl.pdfs_downloaded ?? 0, color: "text-green-600", bg: "from-green-50 to-green-100" },
          { label: "Errors", value: crawl.errors_count ?? 0, color: "text-red-600", bg: "from-red-50 to-red-100" },
        ].map((s) => (
          <div key={s.label} className={`bg-gradient-to-br ${s.bg} rounded-xl p-5`}>
            <div className={`text-3xl font-bold ${s.color}`}>{s.value}</div>
            <div className="text-sm font-medium text-gray-700 mt-1">{s.label}</div>
          </div>
        ))}
      </div>

      {/* Live Log Console */}
      <div className="bg-gray-900 rounded-xl shadow-sm border border-gray-700 overflow-hidden">
        <div className="flex items-center justify-between px-4 py-2 bg-gray-800 border-b border-gray-700">
          <div className="flex items-center gap-2">
            <div className={`h-2 w-2 rounded-full ${isRunning ? "bg-green-400 animate-pulse" : "bg-gray-500"}`} />
            <span className="text-sm font-medium text-gray-300">Crawl Log</span>
            <span className="text-xs text-gray-500">({logs.length} entries)</span>
          </div>
          <button onClick={() => { setLogs([]); setLogIndex(0); }}
            className="text-xs text-gray-500 hover:text-gray-300">Clear</button>
        </div>
        <div ref={logRef}
          className="p-4 font-mono text-xs leading-relaxed overflow-y-auto max-h-80 min-h-40">
          {logs.length === 0 ? (
            <div className="text-gray-600 italic">
              {isRunning ? "Waiting for log entries..." : "No log entries available."}
            </div>
          ) : (
            logs.map((entry, i) => (
              <div key={i} className="py-0.5">
                <span className="text-gray-600">{entry.ts.substring(11, 19)} </span>
                <span className={
                  entry.level === "warn" ? "text-yellow-400" :
                  entry.level === "error" ? "text-red-400" :
                  "text-green-400"
                }>
                  [{entry.level.toUpperCase()}]
                </span>
                {" "}
                <span className="text-gray-200">{entry.msg}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
