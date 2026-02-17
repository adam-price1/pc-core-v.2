import { useEffect, useState, useCallback } from "react";
import { listDocuments, approveDocument, archiveDocument, reclassifyDocument, deleteDocument } from "../api/documents";
import { publishToast } from "../lib/toastBus";
import LoadingSpinner from "../components/LoadingSpinner";
import type { Document } from "../types";

const CLASSIFICATION_OPTIONS = [
  "PDS", "Policy Wording", "Fact Sheet", "TMD", "Product Guide",
  "Certificate of Insurance", "Claim Form", "General Document",
];

const POLICY_TYPE_OPTIONS = [
  "Life", "Home", "Contents", "Motor", "Travel", "Business", "Pet", "Health", "Landlord", "General",
];

export default function Review() {
  const [docs, setDocs] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionId, setActionId] = useState<number | null>(null);
  const [previewDoc, setPreviewDoc] = useState<Document | null>(null);
  const [reclassifyId, setReclassifyId] = useState<number | null>(null);
  const [newClassification, setNewClassification] = useState("");
  const [newPolicyType, setNewPolicyType] = useState("");
  const [tab, setTab] = useState<"needs-review" | "auto-approved" | "validated" | "rejected">("needs-review");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await listDocuments({ limit: 500 });
      setDocs(resp?.items ?? resp?.documents ?? []);
    } catch (err) { console.error("Review load error:", err); }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleApprove = async (docId: number) => {
    setActionId(docId);
    try {
      await approveDocument(docId);
      publishToast({ message: `Document #${docId} approved.`, type: "success" });
      await load();
      // Auto-advance to next needs-review doc
      setPreviewDoc(null);
    } catch (err) { console.error(err); }
    setActionId(null);
  };

  const handleReject = async (docId: number) => {
    setActionId(docId);
    try {
      await archiveDocument(docId);
      publishToast({ message: `Document #${docId} rejected.`, type: "success" });
      await load();
      setPreviewDoc(null);
    } catch (err) { console.error(err); }
    setActionId(null);
  };

  const handleDelete = async (docId: number) => {
    if (!confirm(`Permanently delete document #${docId}?`)) return;
    setActionId(docId);
    try {
      await deleteDocument(docId);
      publishToast({ message: `Document #${docId} deleted.`, type: "success" });
      await load();
      setPreviewDoc(null);
    } catch (err) { console.error(err); }
    setActionId(null);
  };

  const handleReclassify = async (docId: number) => {
    if (!newClassification) return;
    setActionId(docId);
    try {
      await reclassifyDocument(docId, newClassification);
      publishToast({ message: `Reclassified as ${newClassification}.`, type: "success" });
      setReclassifyId(null);
      setNewClassification("");
      setNewPolicyType("");
      await load();
    } catch (err) { console.error(err); }
    setActionId(null);
  };

  const getPreviewUrl = (docId: number) => {
    const token = localStorage.getItem('access_token') || '';
    return `/api/documents/${docId}/preview?token=${encodeURIComponent(token)}`;
  };

  // Navigate to next/prev doc in current list
  const currentList = (() => {
    switch (tab) {
      case "needs-review": return docs.filter((d) => d.status === "needs-review" || d.status === "pending");
      case "auto-approved": return docs.filter((d) => d.status === "auto-approved");
      case "validated": return docs.filter((d) => d.status === "validated");
      case "rejected": return docs.filter((d) => d.status === "rejected");
    }
  })();

  const currentIdx = previewDoc ? currentList.findIndex((d) => d.id === previewDoc.id) : -1;
  const goNext = () => { if (currentIdx < currentList.length - 1) setPreviewDoc(currentList[currentIdx + 1]); };
  const goPrev = () => { if (currentIdx > 0) setPreviewDoc(currentList[currentIdx - 1]); };

  if (loading) return <LoadingSpinner />;

  const needsReview = docs.filter((d) => d.status === "needs-review" || d.status === "pending");
  const autoApproved = docs.filter((d) => d.status === "auto-approved");
  const validated = docs.filter((d) => d.status === "validated");
  const rejected = docs.filter((d) => d.status === "rejected");

  const confColor = (c: number) => c >= 0.85 ? "text-green-600" : c >= 0.7 ? "text-amber-600" : "text-red-600";
  const confBg = (c: number) => c >= 0.85 ? "bg-green-500" : c >= 0.7 ? "bg-amber-500" : "bg-red-500";

  const tabCounts = {
    "needs-review": needsReview.length,
    "auto-approved": autoApproved.length,
    "validated": validated.length,
    "rejected": rejected.length,
  };

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight text-gray-900">Review &amp; Actions</h1>
        <p className="mt-1 text-sm text-gray-600">Human-in-the-loop control for document classification</p>
      </div>

      {/* Summary Stats */}
      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          { key: "needs-review" as const, label: "Needs Review", count: needsReview.length, border: "border-amber-200", bg: "bg-amber-50", color: "text-amber-700", labelColor: "text-amber-600" },
          { key: "auto-approved" as const, label: "Auto-Approved", count: autoApproved.length, border: "border-green-200", bg: "bg-green-50", color: "text-green-700", labelColor: "text-green-600" },
          { key: "validated" as const, label: "Manually Approved", count: validated.length, border: "border-blue-200", bg: "bg-blue-50", color: "text-blue-700", labelColor: "text-blue-600" },
          { key: "rejected" as const, label: "Rejected", count: rejected.length, border: "border-gray-200", bg: "bg-gray-50", color: "text-gray-700", labelColor: "text-gray-600" },
        ].map((s) => (
          <button key={s.key} onClick={() => { setTab(s.key); setPreviewDoc(null); }}
            className={`rounded-xl border p-4 text-center transition-all ${
              tab === s.key ? `${s.border} ${s.bg} ring-2 ring-offset-1 ring-primary-400` : `${s.border} ${s.bg} hover:shadow-sm`
            }`}>
            <div className={`text-2xl font-bold ${s.color}`}>{s.count}</div>
            <div className={`text-xs font-medium ${s.labelColor}`}>{s.label}</div>
          </button>
        ))}
      </div>

      {/* PDF Preview Modal/Panel */}
      {previewDoc && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-6xl h-[85vh] flex flex-col overflow-hidden">
            {/* Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 bg-gray-50">
              <div className="flex items-center gap-4 min-w-0">
                <button onClick={goPrev} disabled={currentIdx <= 0}
                  className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-100 disabled:opacity-30">
                  ← Prev
                </button>
                <div className="min-w-0">
                  <h3 className="text-base font-semibold text-gray-900 truncate">{previewDoc.insurer}</h3>
                  <div className="flex items-center gap-2 text-xs text-gray-500">
                    <span>{previewDoc.classification}</span>
                    <span>·</span>
                    <span>{previewDoc.policy_type}</span>
                    <span>·</span>
                    <span>{previewDoc.country}</span>
                    <span>·</span>
                    <span className={confColor(previewDoc.confidence)}>{((previewDoc.confidence ?? 0) * 100).toFixed(0)}% confidence</span>
                    {previewDoc.file_size && <><span>·</span><span>{(previewDoc.file_size / 1024).toFixed(0)} KB</span></>}
                  </div>
                </div>
                <button onClick={goNext} disabled={currentIdx >= currentList.length - 1}
                  className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-100 disabled:opacity-30">
                  Next →
                </button>
                <span className="text-xs text-gray-400">{currentIdx + 1}/{currentList.length}</span>
              </div>
              <button onClick={() => setPreviewDoc(null)}
                className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-100">
                ✕ Close
              </button>
            </div>
            {/* Content: PDF + Actions sidebar */}
            <div className="flex-1 flex overflow-hidden">
              {/* PDF Viewer */}
              <div className="flex-1 bg-gray-100">
                <iframe
                  src={getPreviewUrl(previewDoc.id)}
                  className="w-full h-full border-0"
                  title={`Preview: ${previewDoc.insurer}`}
                />
              </div>
              {/* Actions Sidebar */}
              <div className="w-72 border-l border-gray-200 p-5 flex flex-col gap-3 overflow-y-auto bg-white">
                <h4 className="text-sm font-semibold text-gray-700 mb-1">Quick Actions</h4>

                {/* Confidence bar */}
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs text-gray-500">Confidence</span>
                    <span className={`text-xs font-semibold ${confColor(previewDoc.confidence)}`}>
                      {((previewDoc.confidence ?? 0) * 100).toFixed(0)}%
                    </span>
                  </div>
                  <div className="h-2 bg-gray-200 rounded-full">
                    <div className={`h-2 rounded-full ${confBg(previewDoc.confidence)}`}
                      style={{ width: `${(previewDoc.confidence ?? 0) * 100}%` }} />
                  </div>
                </div>

                {/* Warnings */}
                {previewDoc.warnings && previewDoc.warnings.length > 0 && (
                  <div className="rounded-lg bg-amber-50 border border-amber-200 p-3">
                    {previewDoc.warnings.map((w, i) => (
                      <div key={i} className="text-xs text-amber-800 flex items-center gap-1 py-0.5">⚠️ {w}</div>
                    ))}
                  </div>
                )}

                {/* Source URL */}
                <div className="text-xs text-gray-400 font-mono truncate" title={previewDoc.source_url}>
                  {previewDoc.source_url}
                </div>

                <div className="border-t border-gray-200 pt-3 space-y-2">
                  <button onClick={() => handleApprove(previewDoc.id)}
                    disabled={actionId === previewDoc.id}
                    className="w-full rounded-lg bg-green-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-green-700 disabled:opacity-50 transition-colors">
                    ✓ Approve &amp; Keep
                  </button>

                  <button onClick={() => {
                    setReclassifyId(previewDoc.id);
                    setNewClassification(previewDoc.classification);
                    setNewPolicyType(previewDoc.policy_type);
                  }}
                    className="w-full rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 transition-colors">
                    ↻ Reclassify
                  </button>

                  {reclassifyId === previewDoc.id && (
                    <div className="rounded-lg border border-gray-200 bg-gray-50 p-3 space-y-2">
                      <div>
                        <label className="text-xs font-medium text-gray-600 mb-0.5 block">Classification</label>
                        <select value={newClassification} onChange={(e) => setNewClassification(e.target.value)}
                          className="w-full rounded-md border border-gray-300 bg-white px-2 py-1.5 text-sm">
                          <option value="">Select...</option>
                          {CLASSIFICATION_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}
                        </select>
                      </div>
                      <div className="flex gap-2">
                        <button onClick={() => handleReclassify(previewDoc.id)}
                          disabled={!newClassification || actionId === previewDoc.id}
                          className="flex-1 rounded-md bg-green-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-700 disabled:opacity-50">
                          Save
                        </button>
                        <button onClick={() => { setReclassifyId(null); setNewClassification(""); }}
                          className="flex-1 rounded-md border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-100">
                          Cancel
                        </button>
                      </div>
                    </div>
                  )}

                  <button onClick={() => handleReject(previewDoc.id)}
                    disabled={actionId === previewDoc.id}
                    className="w-full rounded-lg border-2 border-red-300 px-4 py-2.5 text-sm font-semibold text-red-700 hover:bg-red-50 disabled:opacity-50 transition-colors">
                    ✕ Reject
                  </button>

                  <button onClick={() => handleDelete(previewDoc.id)}
                    disabled={actionId === previewDoc.id}
                    className="w-full rounded-lg border border-gray-300 px-4 py-2 text-xs font-medium text-gray-500 hover:bg-red-50 hover:text-red-600 disabled:opacity-50 transition-colors">
                    🗑 Delete Permanently
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Document List */}
      {currentList.length === 0 ? (
        <div className="rounded-xl border border-gray-200 bg-white py-16 text-center">
          <p className="text-gray-500">
            {docs.length === 0
              ? "No documents to review. Start a crawl first."
              : `No ${tab.replace("-", " ")} documents.`}
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-lg font-semibold text-gray-900">
              {tab === "needs-review" ? "Needs Review" :
               tab === "auto-approved" ? "Auto-Approved" :
               tab === "validated" ? "Manually Approved" : "Rejected"} ({currentList.length})
            </h2>
            <p className="text-xs text-gray-500">Click a document to preview and take action</p>
          </div>
          {currentList.map((doc) => (
            <div key={doc.id}
              onClick={() => setPreviewDoc(doc)}
              className={`rounded-xl border bg-white p-4 shadow-sm cursor-pointer transition-all hover:shadow-md hover:border-primary-300 ${
                previewDoc?.id === doc.id ? "border-primary-400 ring-2 ring-primary-200" : "border-gray-200"
              }`}>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-4 flex-1 min-w-0">
                  <div className="flex-shrink-0 w-10 h-10 rounded-lg bg-red-50 flex items-center justify-center">
                    <span className="text-red-500 text-lg">📄</span>
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 mb-0.5">
                      <h3 className="text-sm font-semibold text-gray-900 truncate">{doc.insurer}</h3>
                      <span className="rounded bg-gray-100 px-2 py-0.5 text-[10px] font-medium text-gray-600">{doc.classification}</span>
                      {doc.status === "auto-approved" && (
                        <span className="rounded bg-green-100 px-1.5 py-0.5 text-[10px] font-semibold text-green-700">AUTO</span>
                      )}
                    </div>
                    <div className="flex items-center gap-2 text-xs text-gray-500">
                      <span>{doc.country}</span>
                      <span>·</span>
                      <span>{doc.policy_type}</span>
                      <span>·</span>
                      <span className={confColor(doc.confidence)}>
                        {((doc.confidence ?? 0) * 100).toFixed(0)}% conf
                      </span>
                      {doc.file_size && (
                        <><span>·</span><span>{(doc.file_size / 1024).toFixed(0)} KB</span></>
                      )}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0 ml-4">
                  {tab === "needs-review" && (
                    <>
                      <button onClick={(e) => { e.stopPropagation(); handleApprove(doc.id); }}
                        disabled={actionId === doc.id}
                        className="rounded-lg bg-green-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-700 disabled:opacity-50">
                        ✓ Approve
                      </button>
                      <button onClick={(e) => { e.stopPropagation(); handleReject(doc.id); }}
                        disabled={actionId === doc.id}
                        className="rounded-lg border border-red-300 px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-50 disabled:opacity-50">
                        ✕ Reject
                      </button>
                    </>
                  )}
                  <span className="text-xs text-primary-600 font-medium">Preview →</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
