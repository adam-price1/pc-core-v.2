import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { startCrawl } from "../api/crawl";

const ALL_POLICY_TYPES = ["Life", "Home", "Motor", "Travel", "Health", "Business"];
const ALL_KEYWORDS = ["PDS", "Policy Wording", "Fact Sheet", "TMD", "Product Guide"];

export default function Setup() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [country, setCountry] = useState("NZ");
  const [seedUrls, setSeedUrls] = useState("");
  const [policyTypes, setPolicyTypes] = useState(["Life", "Home", "Motor"]);
  const [keywords, setKeywords] = useState(["PDS", "Policy Wording", "Fact Sheet", "TMD"]);
  const [maxPages, setMaxPages] = useState(1000);
  const [maxTime, setMaxTime] = useState(60);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");

  function toggleType(type: string) {
    setPolicyTypes((prev) =>
      prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type]
    );
  }

  function toggleKeyword(kw: string) {
    setKeywords((prev) =>
      prev.includes(kw) ? prev.filter((k) => k !== kw) : [...prev, kw]
    );
  }

  async function handleStart() {
    setError("");
    setStarting(true);
    try {
      const config = {
        country,
        seed_urls: seedUrls
          .split("\n")
          .map((u) => u.trim())
          .filter(Boolean),
        policy_types: policyTypes,
        keywords,
        max_pages: maxPages,
        max_time: maxTime,
      };
      const result = await startCrawl(config);
      // Navigate to progress screen with crawl ID
      navigate(`/progress?crawl_id=${result.crawl_id}`);
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail || "Failed to start crawl.";
      setError(msg);
      setStarting(false);
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-5xl mx-auto">
        <div className="mb-6">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">
            Setup &amp; Seed Crawl
          </h1>
          <p className="text-gray-600">
            Define crawl boundaries before running
          </p>
        </div>

        {/* Context Cards */}
        <div className="grid grid-cols-3 gap-6 mb-6">
          <div className="bg-white rounded-xl shadow p-6">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-primary-100 rounded-lg flex items-center justify-center">
                <svg className="w-5 h-5 text-primary-600" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
              </div>
              <div>
                <div className="text-sm text-gray-600">Country</div>
                <div className="font-semibold text-gray-900">{country}</div>
              </div>
            </div>
          </div>
          <div className="bg-white rounded-xl shadow p-6">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-primary-100 rounded-lg flex items-center justify-center">
                <svg className="w-5 h-5 text-primary-600" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
              </div>
              <div>
                <div className="text-sm text-gray-600">Admin</div>
                <div className="font-semibold text-gray-900">{user?.name}</div>
              </div>
            </div>
          </div>
          <div className="bg-white rounded-xl shadow p-6">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-primary-100 rounded-lg flex items-center justify-center">
                <svg className="w-5 h-5 text-primary-600" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
              </div>
              <div>
                <div className="text-sm text-gray-600">Session</div>
                <div className="font-semibold text-gray-900">Active</div>
              </div>
            </div>
          </div>
        </div>

        {/* Configuration Form */}
        <div className="bg-white rounded-xl shadow p-8 mb-6">
          <h2 className="text-xl font-semibold text-gray-900 mb-6">
            Crawl Configuration
          </h2>

          {error && (
            <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">
              {error}
            </div>
          )}

          <div className="space-y-6">
            <div className="grid grid-cols-2 gap-6">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Country
                </label>
                <select
                  value={country}
                  onChange={(e) => setCountry(e.target.value)}
                  className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                >
                  <option value="NZ">New Zealand</option>
                  <option value="AU">Australia</option>
                  <option value="UK">United Kingdom</option>
                  <option value="SG">Singapore</option>
                  <option value="HK">Hong Kong</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Max Pages
                </label>
                <input
                  type="number"
                  value={maxPages}
                  onChange={(e) => setMaxPages(Number(e.target.value))}
                  className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Seed URLs (one per line)
              </label>
              <textarea
                value={seedUrls}
                onChange={(e) => setSeedUrls(e.target.value)}
                placeholder={"https://www.aainsurance.co.nz/products\nhttps://www.ami.co.nz/insurance\nhttps://www.tower.co.nz/products"}
                className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent font-mono text-sm"
                rows={5}
              />
            </div>

            {/* Policy Types Toggle */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Policy Types
              </label>
              <div className="flex flex-wrap gap-2">
                {ALL_POLICY_TYPES.map((type) => (
                  <button
                    key={type}
                    onClick={() => toggleType(type)}
                    className={`px-4 py-2 rounded-lg font-medium transition-all ${
                      policyTypes.includes(type)
                        ? "bg-primary-600 text-white"
                        : "bg-gray-100 text-gray-700 hover:bg-gray-200"
                    }`}
                  >
                    {type}
                  </button>
                ))}
              </div>
            </div>

            {/* Keyword Filters Toggle */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Keyword Filters
              </label>
              <div className="flex flex-wrap gap-2">
                {ALL_KEYWORDS.map((kw) => (
                  <button
                    key={kw}
                    onClick={() => toggleKeyword(kw)}
                    className={`px-4 py-2 rounded-lg font-medium transition-all ${
                      keywords.includes(kw)
                        ? "bg-primary-600 text-white"
                        : "bg-gray-100 text-gray-700 hover:bg-gray-200"
                    }`}
                  >
                    {kw}
                  </button>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-6">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Max Time (minutes)
                </label>
                <input
                  type="number"
                  value={maxTime}
                  onChange={(e) => setMaxTime(Number(e.target.value))}
                  className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                />
              </div>
            </div>
          </div>

          <div className="flex gap-4 mt-8 pt-8 border-t border-gray-200">
            <button
              onClick={handleStart}
              disabled={starting}
              className="flex-1 py-3 bg-gradient-to-r from-primary-600 to-primary-700 text-white rounded-lg font-semibold hover:shadow-lg transition-all flex items-center justify-center gap-2 disabled:opacity-50"
            >
              <svg className="w-5 h-5" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>
              {starting ? "Starting..." : "Start Crawl"}
            </button>
            <button className="px-6 py-3 border border-gray-300 text-gray-700 rounded-lg font-semibold hover:bg-gray-50 transition-all">
              Save Configuration
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
