import { useCallback, useEffect, useState } from 'react';
import {
  downloadAllDocuments,
  downloadDocument,
  searchLibrary,
  exportToCSV,
  getFilterOptions,
  type FilterOptions,
} from '../api/documents';
import { publishToast } from '../lib/toastBus';
import StatusBadge from '../components/StatusBadge';
import type { Document } from '../types';

export default function Library() {
  const [docs, setDocs] = useState<Document[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const [search, setSearch] = useState('');
  const [countryFilter, setCountryFilter] = useState('');
  const [insurerFilter, setInsurerFilter] = useState('');
  const [policyTypeFilter, setPolicyTypeFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [downloadingDocId, setDownloadingDocId] = useState<number | null>(null);
  const [downloadingAll, setDownloadingAll] = useState(false);
  const [filterOptions, setFilterOptions] = useState<FilterOptions>({
    countries: [], insurers: [], policy_types: [], classifications: [], statuses: [],
  });

  useEffect(() => {
    getFilterOptions().then(setFilterOptions).catch(() => {});
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await searchLibrary({
        search: search || undefined,
        country: countryFilter || undefined,
        insurer: insurerFilter || undefined,
        policy_type: policyTypeFilter || undefined,
        status: statusFilter || undefined,
        page,
        limit: 20,
      });
      setDocs(resp?.items ?? resp?.documents ?? []);
      setTotal(resp?.total ?? 0);
      setPages(resp?.pages ?? 1);
    } catch {
      // handled by interceptor
    } finally {
      setLoading(false);
    }
  }, [countryFilter, insurerFilter, policyTypeFilter, statusFilter, page, search]);

  useEffect(() => { load(); }, [load]);

  const handleDownload = async (documentId: number) => {
    setDownloadingDocId(documentId);
    try {
      await downloadDocument(documentId);
      publishToast({ message: 'PDF download started.', type: 'success' });
    } catch (err: any) {
      const msg = err?.message || 'Download failed. File may be missing from storage.';
      publishToast({ message: msg, type: 'error' });
    } finally {
      setDownloadingDocId(null);
    }
  };

  const handleDownloadAll = async () => {
    setDownloadingAll(true);
    try {
      // Pass current filters so only matching documents are downloaded
      const filters: Record<string, string | number | undefined> = {};
      if (countryFilter) filters.country = countryFilter;
      if (insurerFilter) filters.insurer = insurerFilter;
      if (policyTypeFilter) filters.policy_type = policyTypeFilter;
      if (statusFilter) filters.status = statusFilter;
      if (search) filters.search = search;

      await downloadAllDocuments(Object.keys(filters).length > 0 ? filters : undefined);
      publishToast({ message: hasFilters ? 'Filtered ZIP download started.' : 'ZIP download started.', type: 'success' });
    } catch (err: any) {
      const msg = err?.message || 'ZIP download failed. Files may be missing from storage.';
      publishToast({ message: msg, type: 'error' });
    } finally {
      setDownloadingAll(false);
    }
  };

  const handleExportCSV = () => {
    if (docs.length === 0) return;
    exportToCSV(docs);
    publishToast({ message: 'CSV exported.', type: 'success' });
  };

  const resetFilters = () => {
    setSearch('');
    setCountryFilter('');
    setInsurerFilter('');
    setPolicyTypeFilter('');
    setStatusFilter('');
    setPage(1);
  };

  const hasFilters = !!(search || countryFilter || insurerFilter || policyTypeFilter || statusFilter);

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight text-gray-900">Policy Library</h1>
        <p className="mt-1 text-sm text-gray-500">{total} documents</p>
      </div>

      {/* Filters */}
      <div className="mb-5 flex flex-wrap items-center gap-3">
        <input
          type="text"
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1); }}
          placeholder="Search..."
          className="rounded-lg border border-gray-300 px-3 py-2 text-sm"
        />
        <select value={countryFilter} onChange={(e) => { setCountryFilter(e.target.value); setPage(1); }} className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm">
          <option value="">All Countries</option>
          {filterOptions.countries.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <select value={insurerFilter} onChange={(e) => { setInsurerFilter(e.target.value); setPage(1); }} className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm">
          <option value="">All Insurers</option>
          {filterOptions.insurers.map((i) => <option key={i} value={i}>{i}</option>)}
        </select>
        <select value={policyTypeFilter} onChange={(e) => { setPolicyTypeFilter(e.target.value); setPage(1); }} className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm">
          <option value="">All Policy Types</option>
          {filterOptions.policy_types.map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
        <select value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }} className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm">
          <option value="">All Statuses</option>
          {filterOptions.statuses.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        {hasFilters && (
          <button onClick={resetFilters} className="rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-600 hover:bg-gray-100">
            Clear Filters
          </button>
        )}
        <div className="ml-auto flex gap-2">
          <button
            onClick={handleExportCSV}
            disabled={docs.length === 0}
            className="inline-flex items-center gap-2 rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          >
            Export CSV
          </button>
          <button
            onClick={handleDownloadAll}
            disabled={downloadingAll || total === 0}
            className="inline-flex items-center gap-2 rounded-lg bg-primary-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-primary-700 disabled:opacity-50"
          >
            {downloadingAll ? "Downloading..." : hasFilters ? `Download Filtered (${total})` : `Download All (${total})`}
          </button>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <div className="h-12 w-12 animate-spin rounded-full border-4 border-gray-200 border-t-primary-600" />
        </div>
      ) : docs.length === 0 ? (
        <div className="rounded-xl border border-gray-200 bg-white py-16 text-center">
          <p className="text-gray-500">No documents found.</p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {docs.map((doc) => (
            <div key={doc.id} className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm transition-all hover:shadow-md">
              <div className="mb-3 flex items-start justify-between">
                <div className="flex items-center gap-2">
                  <StatusBadge status={doc.status} />
                  {doc.status === 'auto-approved' && (
                    <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-medium text-emerald-700">AUTO</span>
                  )}
                </div>
                <span className="text-xs text-gray-400">{doc.country}</span>
              </div>
              <h3 className="mb-1 line-clamp-2 text-sm font-semibold text-gray-900">{doc.insurer}</h3>
              <p className="mb-3 text-xs text-gray-500">
                {doc.classification} / {doc.policy_type}
              </p>
              <div className="mb-4 text-xs text-gray-400">
                Confidence: {((doc.confidence ?? 0) * 100).toFixed(0)}%
                {doc.file_size ? ` · ${(doc.file_size / 1024).toFixed(0)} KB` : ''}
              </div>
              <button
                onClick={() => handleDownload(doc.id)}
                disabled={downloadingDocId === doc.id}
                className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-gray-100 px-3 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-200 disabled:opacity-50"
              >
                {downloadingDocId === doc.id ? "Downloading..." : "Download PDF"}
              </button>
            </div>
          ))}
        </div>
      )}

      {pages > 1 && (
        <div className="mt-6 flex items-center justify-between">
          <span className="text-sm text-gray-500">Page {page} of {pages}</span>
          <div className="flex gap-2">
            <button
              onClick={() => setPage((c) => Math.max(1, c - 1))}
              disabled={page === 1}
              className="rounded-md border border-gray-300 px-3 py-1 text-sm disabled:opacity-40"
            >
              Previous
            </button>
            <button
              onClick={() => setPage((c) => Math.min(pages, c + 1))}
              disabled={page === pages}
              className="rounded-md border border-gray-300 px-3 py-1 text-sm disabled:opacity-40"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
