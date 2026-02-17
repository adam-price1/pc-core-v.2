import React, { useState, useRef } from 'react';
import { publishToast } from '../lib/toastBus';
import { documentsApi } from '../api/documents';

const COUNTRIES = ['NZ', 'AU', 'US', 'UK', 'CA', 'SG', 'HK'];
const POLICY_TYPES = [
  'General',
  'Motor',
  'Home',
  'Contents',
  'Travel',
  'Life',
  'Health',
  'Business',
  'Landlord',
  'Pet',
  'Marine',
  'Liability',
  'Other',
];

export default function Upload() {
  const [file, setFile] = useState<File | null>(null);
  const [country, setCountry] = useState('NZ');
  const [insurer, setInsurer] = useState('');
  const [policyType, setPolicyType] = useState('General');
  const [uploading, setUploading] = useState(false);
  const [lastResult, setLastResult] = useState<{
    id: number;
    classification: string;
    policy_type: string;
    confidence: number;
  } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0] ?? null;
    if (selected && !selected.name.toLowerCase().endsWith('.pdf')) {
      publishToast({ message: 'Only PDF files are allowed', type: 'error' });
      e.target.value = '';
      return;
    }
    setFile(selected);
    setLastResult(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) {
      publishToast({ message: 'Please select a PDF file', type: 'error' });
      return;
    }

    setUploading(true);
    try {
      const doc = await documentsApi.uploadDocument(
        file,
        country,
        insurer || undefined,
        policyType,
      );
      setLastResult({
        id: doc.id,
        classification: doc.classification || doc.document_type || 'Unclassified',
        policy_type: doc.policy_type || 'General',
        confidence: doc.confidence ?? 0,
      });
      publishToast({
        message: `Uploaded & classified! Doc #${doc.id}: ${doc.classification} (${((doc.confidence ?? 0) * 100).toFixed(0)}%)`,
        type: 'success',
      });
      // Reset form
      setFile(null);
      setInsurer('');
      setPolicyType('General');
      if (fileInputRef.current) fileInputRef.current.value = '';
    } catch {
      publishToast({ message: 'Upload failed. Please try again.', type: 'error' });
    } finally {
      setUploading(false);
    }
  };

  const confColor = (c: number) =>
    c >= 0.85 ? 'text-green-700 bg-green-50 border-green-200' :
    c >= 0.5 ? 'text-amber-700 bg-amber-50 border-amber-200' :
    'text-red-700 bg-red-50 border-red-200';

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight text-gray-900">Upload Document</h1>
        <p className="mt-1 text-sm text-gray-500">Upload policy PDFs for auto-classification and review</p>
      </div>

      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
        <p className="text-blue-800 text-sm">
          <strong>Auto-Classification:</strong> Uploaded PDFs are automatically scanned to detect
          the document type (PDS, Policy Wording, TMD, etc.) and policy category
          (Motor, Home, Contents, etc.). You can always reclassify on the Review page.
        </p>
      </div>

      {lastResult && (
        <div className={`mb-6 rounded-lg border p-4 ${confColor(lastResult.confidence)}`}>
          <p className="font-medium">
            Document #{lastResult.id} classified as:{' '}
            <span className="font-bold">{lastResult.classification}</span> /{' '}
            <span className="font-bold">{lastResult.policy_type}</span>
          </p>
          <p className="text-sm mt-1">
            Confidence: {(lastResult.confidence * 100).toFixed(0)}% —
            {lastResult.confidence >= 0.85
              ? ' Auto-approved'
              : ' Needs manual review'}
          </p>
        </div>
      )}

      <form
        onSubmit={handleSubmit}
        className="bg-white shadow rounded-xl border border-gray-200 p-6 max-w-lg space-y-5"
      >
        {/* File Input */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            PDF File <span className="text-red-500">*</span>
          </label>
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,application/pdf"
            onChange={handleFileChange}
            className="block w-full text-sm text-gray-600 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-medium file:bg-primary-50 file:text-primary-700 hover:file:bg-primary-100"
          />
          {file && (
            <p className="mt-1 text-xs text-gray-500">
              {file.name} ({(file.size / 1024).toFixed(1)} KB)
            </p>
          )}
        </div>

        {/* Country */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Country</label>
          <select
            value={country}
            onChange={(e) => setCountry(e.target.value)}
            className="block w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm focus:ring-primary-500 focus:border-primary-500"
          >
            {COUNTRIES.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </div>

        {/* Insurer */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Insurer</label>
          <input
            type="text"
            value={insurer}
            onChange={(e) => setInsurer(e.target.value)}
            placeholder="e.g. AA Insurance, Tower, AMI"
            className="block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-primary-500 focus:border-primary-500"
          />
          <p className="mt-1 text-xs text-gray-400">Leave blank to use &quot;Manual Upload&quot;</p>
        </div>

        {/* Policy Type */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Policy Type
            <span className="text-xs text-gray-400 ml-2">(auto-detected if left as General)</span>
          </label>
          <select
            value={policyType}
            onChange={(e) => setPolicyType(e.target.value)}
            className="block w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm focus:ring-primary-500 focus:border-primary-500"
          >
            {POLICY_TYPES.map((pt) => (
              <option key={pt} value={pt}>{pt}</option>
            ))}
          </select>
        </div>

        {/* Submit */}
        <button
          type="submit"
          disabled={uploading || !file}
          className="w-full inline-flex justify-center items-center px-4 py-2.5 border border-transparent text-sm font-semibold rounded-lg text-white bg-primary-600 hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 disabled:opacity-50 disabled:cursor-not-allowed shadow-sm transition-colors"
        >
          {uploading ? 'Uploading & Classifying…' : 'Upload PDF'}
        </button>
      </form>
    </div>
  );
}
