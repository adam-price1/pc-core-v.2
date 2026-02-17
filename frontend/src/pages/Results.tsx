import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  downloadAllDocuments,
  downloadDocument,
  listDocuments,
} from '../api/documents';
import { publishToast } from '../lib/toastBus';
import StatusBadge from '../components/StatusBadge';
import type { Document } from '../types';

export default function Results() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const crawlIdParam = searchParams.get('crawl_id');
  const crawlSessionId = useMemo(() => {
    const parsed = Number(crawlIdParam);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : undefined;
  }, [crawlIdParam]);

  const [docs, setDocs] = useState<Document[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [downloadingDocId, setDownloadingDocId] = useState<number | null>(null);
  const [downloadingAll, setDownloadingAll] = useState(false);

  useEffect(() => {
    setLoading(true);
    listDocuments({
      limit: 100,
      crawl_session_id: crawlSessionId,
    })
      .then((resp) => {
        setDocs(resp?.items ?? resp?.documents ?? []);
        setTotal(resp?.total ?? 0);
      })
      .catch(() => {
        // Error toast is handled centrally by the Axios interceptor.
      })
      .finally(() => setLoading(false));
  }, [crawlSessionId]);

  const handleDownload = async (documentId: number) => {
    setDownloadingDocId(documentId);
    try {
      await downloadDocument(documentId);
      publishToast({ message: 'PDF download started.', type: 'success' });
    } catch {
      // Error toast is handled centrally by the Axios interceptor.
    } finally {
      setDownloadingDocId(null);
    }
  };

  const handleDownloadAll = async () => {
    setDownloadingAll(true);
    try {
      await downloadAllDocuments(
        crawlSessionId ? { crawl_session_id: crawlSessionId } : undefined,
      );
      publishToast({ message: 'ZIP download started.', type: 'success' });
    } catch {
      // Error toast is handled centrally by the Axios interceptor.
    } finally {
      setDownloadingAll(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="text-center">
          <svg
            className="mx-auto h-12 w-12 animate-spin text-primary-600"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.37 0 0 5.37 0 12h4zm2 5.29A7.95 7.95 0 014 12H0c0 3.04 1.13 5.82 3 7.94l3-2.65z"
            />
          </svg>
          <p className="mt-3 text-sm text-gray-500">Loading crawl results...</p>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-8">
        <h1 className="mb-1 text-2xl font-bold text-gray-900">Crawl Results</h1>
        <p className="text-gray-600">
          {total} documents discovered
          {crawlSessionId ? ` in crawl #${crawlSessionId}` : ''}
        </p>
      </div>

      <div className="mb-6 flex flex-wrap items-center gap-3">
        <button
          onClick={() => navigate('/review')}
          className="rounded-lg bg-primary-600 px-4 py-2 font-medium text-white hover:bg-primary-700"
        >
          Review Documents
        </button>
        <button
          onClick={() => navigate('/library')}
          className="rounded-lg border border-gray-300 px-4 py-2 font-medium text-gray-700 hover:bg-gray-50"
        >
          View Library
        </button>
        <button
          onClick={handleDownloadAll}
          disabled={downloadingAll || docs.length === 0}
          className="ml-auto inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
        >
          {downloadingAll ? (
            <>
              <svg className="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.37 0 0 5.37 0 12h4zm2 5.29A7.95 7.95 0 014 12H0c0 3.04 1.13 5.82 3 7.94l3-2.65z"
                />
              </svg>
              Downloading...
            </>
          ) : (
            <>
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
                />
              </svg>
              Download All ({total})
            </>
          )}
        </button>
      </div>

      {docs.length === 0 ? (
        <div className="rounded-xl border border-gray-200 bg-white py-16 text-center">
          <p className="text-gray-500">No documents found.</p>
        </div>
      ) : (
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {docs.map((doc) => (
            <div
              key={doc.id}
              className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm transition-all hover:shadow-lg"
            >
              <div className="mb-3 flex items-start justify-between">
                <StatusBadge status={doc.status} />
                <span className="text-xs text-gray-400">{doc.country}</span>
              </div>
              <h3 className="mb-2 line-clamp-2 text-sm font-semibold text-gray-900">{doc.insurer}</h3>
              <div className="mb-4 space-y-1">
                <p className="text-xs text-gray-500">
                  <span className="font-medium">Type:</span> {doc.policy_type}
                </p>
                <p className="text-xs text-gray-500">
                  <span className="font-medium">Classification:</span> {doc.classification}
                </p>
                <p className="text-xs text-gray-500">
                  <span className="font-medium">Confidence:</span>{' '}
                  {((doc.confidence ?? 0) * 100).toFixed(0)}%
                </p>
              </div>
              <button
                onClick={() => handleDownload(doc.id)}
                disabled={downloadingDocId === doc.id}
                className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-gray-100 px-3 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-200 disabled:opacity-50"
              >
                {downloadingDocId === doc.id ? (
                  <>
                    <svg className="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
                      <circle
                        className="opacity-25"
                        cx="12"
                        cy="12"
                        r="10"
                        stroke="currentColor"
                        strokeWidth="4"
                      />
                      <path
                        className="opacity-75"
                        fill="currentColor"
                        d="M4 12a8 8 0 018-8V0C5.37 0 0 5.37 0 12h4zm2 5.29A7.95 7.95 0 014 12H0c0 3.04 1.13 5.82 3 7.94l3-2.65z"
                      />
                    </svg>
                    Downloading...
                  </>
                ) : (
                  <>
                    <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
                      />
                    </svg>
                    Download PDF
                  </>
                )}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
