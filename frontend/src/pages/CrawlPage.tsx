import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { startCrawl, deleteCrawl, listCrawlSessions, addCustomInsurer, removeCustomInsurer } from "../api/crawl";
import client from "../api/client";
import { publishToast } from "../lib/toastBus";
import StatusBadge from "../components/StatusBadge";
import { useAuth } from "../context/AuthContext";
import type { CrawlStatusResponse } from "../types";

interface InsurerEntry {
  insurer: string;
  seed_urls: string[];
  policy_types: string[];
  country: string;
  is_custom?: boolean;
}

const POLICY_TYPES = ["Life", "Home", "Contents", "Motor", "Travel", "Business", "Pet", "Health", "Landlord"];
const KEYWORDS = ["PDS", "Policy Wording", "Fact Sheet", "TMD", "policy", "insurance", "wording", "document"];

export default function CrawlPage() {
  const navigate = useNavigate();
  const { isAdmin } = useAuth();
  const [country, setCountry] = useState("NZ");
  const [insurers, setInsurers] = useState<InsurerEntry[]>([]);
  const [selectedInsurers, setSelectedInsurers] = useState<Set<string>>(new Set());
  const [customUrls, setCustomUrls] = useState("");
  const [maxPages, setMaxPages] = useState(200);
  const [maxTime, setMaxTime] = useState(60);
  const [starting, setStarting] = useState(false);
  const [loadingSeeds, setLoadingSeeds] = useState(false);
  const [sessions, setSessions] = useState<CrawlStatusResponse[]>([]);
  const [error, setError] = useState("");
  const [deleting, setDeleting] = useState<number | null>(null);
  const [resetting, setResetting] = useState(false);
  const [showCustom, setShowCustom] = useState(false);
  const [showSeedUrls, setShowSeedUrls] = useState(false);

  // Custom insurer form state
  const [newInsurerName, setNewInsurerName] = useState("");
  const [newInsurerUrls, setNewInsurerUrls] = useState("");
  const [savingInsurer, setSavingInsurer] = useState(false);

  const loadSessions = useCallback(async () => {
    try { setSessions(await listCrawlSessions()); } catch { /* */ }
  }, []);

  const loadInsurers = useCallback(async (c: string) => {
    setLoadingSeeds(true);
    try {
      const res = await client.get(`/api/crawl/seed-urls?country=${c}`);
      const list: InsurerEntry[] = res.data.insurers || [];
      setInsurers(list);
      // Don't select any by default - user picks what they want
      setSelectedInsurers(new Set());
    } catch {
      setInsurers([]);
      setSelectedInsurers(new Set());
    }
    setLoadingSeeds(false);
  }, []);

  useEffect(() => { loadSessions(); }, [loadSessions]);
  useEffect(() => { loadInsurers(country); }, [country, loadInsurers]);

  const toggleInsurer = (name: string) => {
    setSelectedInsurers((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name); else next.add(name);
      return next;
    });
  };

  const selectAll = () => setSelectedInsurers(new Set(insurers.map((i) => i.insurer)));
  const selectNone = () => setSelectedInsurers(new Set());

  const getSelectedUrls = (): string[] => {
    const urls: string[] = [];
    for (const ins of insurers) {
      if (selectedInsurers.has(ins.insurer)) {
        urls.push(...ins.seed_urls);
      }
    }
    // Add custom URLs
    if (customUrls.trim()) {
      urls.push(...customUrls.split("\n").map((u) => u.trim()).filter(Boolean));
    }
    return urls;
  };

  async function handleStart() {
    const urls = getSelectedUrls();
    if (urls.length === 0) {
      setError("Select at least one insurer or add custom URLs");
      return;
    }
    setError("");
    setStarting(true);
    try {
      const config = {
        country,
        seed_urls: urls,
        policy_types: POLICY_TYPES,
        keywords: KEYWORDS,
        max_pages: maxPages,
        max_time: maxTime,
      };
      const result = await startCrawl(config);
      publishToast({ message: `Crawl #${result.crawl_id} started!`, type: "success" });
      navigate(`/progress?crawl_id=${result.crawl_id}`);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to start crawl";
      setError(msg);
      publishToast({ message: msg, type: "error" });
    }
    setStarting(false);
  }

  async function handleDelete(crawlId: number) {
    if (!confirm(`Delete crawl #${crawlId} and its documents?`)) return;
    setDeleting(crawlId);
    try {
      await deleteCrawl(crawlId);
      publishToast({ message: `Crawl #${crawlId} deleted`, type: "success" });
      await loadSessions();
    } catch { /* */ }
    setDeleting(null);
  }

  async function handleReset() {
    if (!confirm("Reset entire system? This deletes ALL crawls, documents, and files.")) return;
    if (!confirm("Are you absolutely sure? This cannot be undone.")) return;
    setResetting(true);
    try {
      const res = await client.delete("/api/system/reset");
      publishToast({ message: res.data.message || "System reset complete", type: "success" });
      await loadSessions();
    } catch { /* */ }
    setResetting(false);
  }

  async function handleSaveCustomInsurer() {
    if (!newInsurerName.trim()) {
      publishToast({ message: "Enter an insurer name", type: "error" });
      return;
    }
    const urls = newInsurerUrls.split("\n").map((u) => u.trim()).filter((u) => u.startsWith("http"));
    if (urls.length === 0) {
      publishToast({ message: "Enter at least one valid URL (must start with http)", type: "error" });
      return;
    }
    setSavingInsurer(true);
    try {
      await addCustomInsurer(country, newInsurerName.trim(), urls);
      publishToast({ message: `Saved custom insurer: ${newInsurerName.trim()}`, type: "success" });
      setNewInsurerName("");
      setNewInsurerUrls("");
      await loadInsurers(country);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to save insurer";
      publishToast({ message: msg, type: "error" });
    }
    setSavingInsurer(false);
  }

  async function handleDeleteCustomInsurer(insurerName: string) {
    if (!confirm(`Remove custom insurer "${insurerName}"?`)) return;
    try {
      await removeCustomInsurer(country, insurerName);
      publishToast({ message: `Removed: ${insurerName}`, type: "success" });
      setSelectedInsurers((prev) => {
        const next = new Set(prev);
        next.delete(insurerName);
        return next;
      });
      await loadInsurers(country);
    } catch {
      publishToast({ message: "Failed to remove insurer", type: "error" });
    }
  }

  const selectedCount = selectedInsurers.size;
  const selectedUrlCount = getSelectedUrls().length;
  const selectedSeedUrls = getSelectedUrls();

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-gray-900">Crawl Manager</h1>
          <p className="mt-1 text-sm text-gray-500">Configure and trigger web crawls to discover insurance policy documents</p>
        </div>
        <div className="flex gap-3">
          {sessions.some((s) => s.status === "running") && (
            <button onClick={() => navigate("/progress")}
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700">
              View Progress
            </button>
          )}
          {isAdmin && (
            <button onClick={handleReset} disabled={resetting}
              className="rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-50">
              {resetting ? "Resetting..." : "Reset System"}
            </button>
          )}
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Config Panel - takes 2 cols */}
        <div className="lg:col-span-2 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="mb-4 text-lg font-semibold text-gray-900">Crawl Configuration</h2>

          {error && <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}

          {/* Country */}
          <label className="mb-1 block text-sm font-medium text-gray-700">Country</label>
          <select value={country} onChange={(e) => setCountry(e.target.value)}
            className="mb-4 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm">
            <option value="NZ">New Zealand</option>
            <option value="AU">Australia</option>
            <option value="UK">United Kingdom</option>
          </select>

          {/* Insurer Selector */}
          <div className="mb-4">
            <div className="flex items-center justify-between mb-2">
              <label className="text-sm font-medium text-gray-700">
                Select Insurers ({selectedCount}/{insurers.length} selected, {selectedUrlCount} seed URLs)
              </label>
              <div className="flex gap-2">
                <button onClick={selectAll} className="text-xs text-primary-600 hover:text-primary-800 font-medium">Select All</button>
                <span className="text-xs text-gray-400">|</span>
                <button onClick={selectNone} className="text-xs text-gray-500 hover:text-gray-700 font-medium">Clear</button>
              </div>
            </div>
            {loadingSeeds ? (
              <div className="flex items-center gap-2 py-4 text-sm text-gray-500">
                <div className="h-4 w-4 animate-spin rounded-full border-2 border-primary-500 border-r-transparent" />
                Loading insurers...
              </div>
            ) : (
              <div className="grid grid-cols-2 md:grid-cols-3 gap-1.5 max-h-56 overflow-y-auto rounded-lg border border-gray-200 p-3 bg-gray-50">
                {insurers.map((ins) => (
                  <label key={ins.insurer}
                    className={`flex items-center gap-2 rounded-md px-2 py-1.5 text-sm cursor-pointer transition-colors ${
                      selectedInsurers.has(ins.insurer) ? "bg-primary-50 text-primary-800" : "hover:bg-gray-100 text-gray-600"
                    }`}>
                    <input type="checkbox" checked={selectedInsurers.has(ins.insurer)}
                      onChange={() => toggleInsurer(ins.insurer)}
                      className="rounded border-gray-300 text-primary-600 focus:ring-primary-500" />
                    <span className="truncate">{ins.insurer}</span>
                    {ins.is_custom && (
                      <span className="ml-0.5 rounded bg-amber-100 px-1 py-0 text-[10px] font-semibold text-amber-700">Custom</span>
                    )}
                    <span className="ml-auto text-xs text-gray-400 flex items-center gap-1">
                      {ins.seed_urls.length}
                      {ins.is_custom && (
                        <button
                          onClick={(e) => { e.preventDefault(); e.stopPropagation(); handleDeleteCustomInsurer(ins.insurer); }}
                          className="text-red-400 hover:text-red-600 ml-0.5"
                          title="Remove custom insurer"
                        >
                          ✕
                        </button>
                      )}
                    </span>
                  </label>
                ))}
              </div>
            )}
          </div>

          {/* Custom Insurer Management */}
          <div className="mb-4">
            <button onClick={() => setShowCustom(!showCustom)}
              className="text-xs font-medium text-gray-500 hover:text-gray-700">
              {showCustom ? "▼ Hide" : "▶ Add"} custom seed URLs / insurers
            </button>
            {showCustom && (
              <div className="mt-2 space-y-3 rounded-lg border border-gray-200 bg-gray-50 p-3">
                {/* Add permanent custom insurer */}
                <div>
                  <p className="text-xs font-semibold text-gray-600 mb-1.5">Save a permanent custom insurer</p>
                  <input
                    value={newInsurerName}
                    onChange={(e) => setNewInsurerName(e.target.value)}
                    placeholder="Insurer name (e.g. My Custom Insurer)"
                    className="w-full rounded-md border border-gray-300 px-2.5 py-1.5 text-sm mb-1.5"
                  />
                  <textarea
                    value={newInsurerUrls}
                    onChange={(e) => setNewInsurerUrls(e.target.value)}
                    rows={3}
                    placeholder={"https://example.com/insurance/car\nhttps://example.com/insurance/home"}
                    className="w-full rounded-md border border-gray-300 px-2.5 py-1.5 font-mono text-xs"
                  />
                  <button
                    onClick={handleSaveCustomInsurer}
                    disabled={savingInsurer}
                    className="mt-1.5 rounded-md bg-primary-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-primary-700 disabled:opacity-50"
                  >
                    {savingInsurer ? "Saving..." : "Save Insurer Permanently"}
                  </button>
                </div>
                {/* One-time custom URLs */}
                <div className="border-t border-gray-200 pt-3">
                  <p className="text-xs font-semibold text-gray-600 mb-1.5">Or add one-time URLs for this crawl only</p>
                  <textarea value={customUrls} onChange={(e) => setCustomUrls(e.target.value)}
                    rows={2} placeholder="Enter additional URLs, one per line"
                    className="w-full rounded-md border border-gray-300 px-2.5 py-1.5 font-mono text-xs" />
                </div>
              </div>
            )}
          </div>

          {/* Show selected seed URLs */}
          {selectedUrlCount > 0 && (
            <div className="mb-4">
              <button onClick={() => setShowSeedUrls(!showSeedUrls)}
                className="text-xs font-medium text-primary-600 hover:text-primary-800">
                {showSeedUrls ? "▼ Hide" : "▶ Show"} {selectedUrlCount} seed URLs to crawl
              </button>
              {showSeedUrls && (
                <div className="mt-2 rounded-lg border border-gray-200 bg-gray-50 p-3 max-h-40 overflow-y-auto">
                  {selectedSeedUrls.map((url, i) => (
                    <div key={i} className="text-xs font-mono text-gray-600 py-0.5 truncate" title={url}>
                      {url}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Max Pages + Timeout */}
          <div className="mb-4 grid grid-cols-2 gap-4">
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">Max Pages (total)</label>
              <input type="number" value={maxPages} onChange={(e) => setMaxPages(Number(e.target.value))}
                min={1} max={500000} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
              <p className="mt-1 text-xs text-gray-400">
                ~{selectedCount > 0 ? Math.max(3, Math.floor(maxPages / selectedCount)) : maxPages} pages per insurer
              </p>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">Timeout (min)</label>
              <input type="number" value={maxTime} onChange={(e) => setMaxTime(Number(e.target.value))}
                min={1} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
            </div>
          </div>

          {/* Tags */}
          <div className="mb-4 rounded-lg bg-gray-50 p-3">
            <p className="mb-1 text-xs font-medium text-gray-600">Policy Types</p>
            <div className="flex flex-wrap gap-1.5">
              {POLICY_TYPES.map((t) => (
                <span key={t} className="rounded-full bg-primary-100 px-2.5 py-0.5 text-xs font-medium text-primary-700">{t}</span>
              ))}
            </div>
            <p className="mb-1 mt-2 text-xs font-medium text-gray-600">Keywords</p>
            <div className="flex flex-wrap gap-1.5">
              {KEYWORDS.map((k) => (
                <span key={k} className="rounded-full bg-gray-200 px-2.5 py-0.5 text-xs font-medium text-gray-700">{k}</span>
              ))}
            </div>
          </div>

          <button onClick={handleStart}
            disabled={starting || selectedUrlCount === 0}
            className="w-full rounded-lg bg-primary-600 py-2.5 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-primary-700 disabled:opacity-50">
            {starting ? "Starting..." : `Start Crawl (${selectedUrlCount} seed URLs)`}
          </button>
        </div>

        {/* Right sidebar - Crawl History */}
        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="mb-4 text-lg font-semibold text-gray-900">Crawl History</h2>
          {sessions.length === 0 ? (
            <p className="text-sm text-gray-500">No crawls yet.</p>
          ) : (
            <div className="space-y-2 max-h-[32rem] overflow-y-auto">
              {sessions.map((s) => (
                <div key={s.id} className="rounded-lg border border-gray-100 px-3 py-2.5 text-sm">
                  <div className="flex items-center justify-between">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-gray-800">#{s.id}</span>
                        <StatusBadge status={s.status} />
                      </div>
                      <div className="text-xs text-gray-400 mt-0.5">
                        {s.country} · {s.pdfs_downloaded ?? 0} PDFs · {s.progress_pct}%
                      </div>
                      <div className="text-xs text-gray-400 mt-0.5">
                        {s.pages_scanned ?? 0} pages · {s.seed_urls_crawled?.length ?? 0} seed URLs
                      </div>
                      {s.insurers_list && s.insurers_list.length > 0 && (
                        <div className="mt-1 flex flex-wrap gap-1">
                          {s.insurers_list.slice(0, 4).map((name) => (
                            <span key={name} className="rounded bg-blue-50 px-1.5 py-0 text-[10px] font-medium text-blue-700">
                              {name}
                            </span>
                          ))}
                          {s.insurers_list.length > 4 && (
                            <span className="text-[10px] text-gray-400">+{s.insurers_list.length - 4} more</span>
                          )}
                        </div>
                      )}
                    </div>
                    <div className="flex gap-1 flex-shrink-0 ml-2">
                      {s.status === "running" ? (
                        <button onClick={() => navigate(`/progress?crawl_id=${s.id}`)}
                          className="rounded bg-blue-100 px-2 py-1 text-xs font-medium text-blue-700 hover:bg-blue-200">
                          Live
                        </button>
                      ) : (
                        <>
                          <button onClick={() => navigate(`/progress?crawl_id=${s.id}`)}
                            className="rounded bg-gray-100 px-2 py-1 text-xs font-medium text-gray-600 hover:bg-gray-200">
                            View
                          </button>
                          <button onClick={() => handleDelete(s.id)}
                            disabled={deleting === s.id}
                            className="rounded bg-red-50 px-2 py-1 text-xs font-medium text-red-600 hover:bg-red-100 disabled:opacity-50">
                            {deleting === s.id ? "..." : "Del"}
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
