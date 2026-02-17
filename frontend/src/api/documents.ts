/**
 * Documents API functions.
 */
import client from './client';
import type { Document } from '../types';

export interface DocumentFilters {
  status?: string;
  classification?: string;
  country?: string;
  insurer?: string;
  policy_type?: string;
  min_confidence?: number;
  skip?: number;
  limit?: number;
  page?: number;
  search?: string;
  crawl_session_id?: number;
  date_from?: string;
  date_to?: string;
}

export interface DocumentListResponse {
  documents: Document[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
  /* computed helpers for the UI */
  items: Document[];
  pages: number;
  page: number;
  page_size: number;
}

export interface FilterOptions {
  countries: string[];
  insurers: string[];
  policy_types: string[];
  classifications: string[];
  statuses: string[];
}

const EMPTY_RESPONSE: DocumentListResponse = {
  documents: [],
  total: 0,
  limit: 20,
  offset: 0,
  has_more: false,
  items: [],
  pages: 1,
  page: 1,
  page_size: 20,
};

function extractFilename(contentDisposition: string | undefined, fallback: string): string {
  if (!contentDisposition) return fallback;
  const utf8Match = /filename\*=UTF-8''([^;]+)/i.exec(contentDisposition);
  if (utf8Match?.[1]) {
    try { return decodeURIComponent(utf8Match[1]); } catch { return utf8Match[1]; }
  }
  const plainMatch = /filename="?([^"]+)"?/i.exec(contentDisposition);
  if (plainMatch?.[1]) return plainMatch[1];
  return fallback;
}

function triggerBrowserDownload(blob: Blob, filename: string): void {
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
}

export const getDocumentDownloadUrl = (documentId: number, token?: string): string => {
  const baseUrl = import.meta.env.VITE_API_URL || '';
  const url = `${baseUrl}/api/documents/${documentId}/download`;
  if (!token) return url;
  return `${url}?token=${encodeURIComponent(token)}`;
};

export const downloadDocument = async (documentId: number): Promise<void> => {
  const response = await client.get(`/api/documents/${documentId}/download`, {
    responseType: 'blob',
    validateStatus: (status) => status < 500,
  });
  
  if (response.status === 404) {
    throw new Error(
      'PDF file not found on disk. The file may have been removed. ' +
      'Try re-running the crawl to re-download this document.'
    );
  }
  
  if (response.status !== 200) {
    throw new Error(`Download failed with status ${response.status}`);
  }
  
  const contentDisposition = String(response.headers?.['content-disposition'] ?? '');
  const filename = extractFilename(contentDisposition, `document_${documentId}.pdf`);
  const blob = new Blob([response.data], { type: 'application/pdf' });
  triggerBrowserDownload(blob, filename);
};

export const downloadAllDocuments = async (filters?: {
  crawl_session_id?: number;
  country?: string;
  policy_type?: string;
  status?: string;
  insurer?: string;
  classification?: string;
  search?: string;
  min_confidence?: number;
}): Promise<void> => {
  const response = await client.get('/api/documents/download-all/zip', {
    params: filters || undefined,
    responseType: 'blob',
    validateStatus: (status) => status < 500,
  });
  
  // Check for error responses (404 = no files available)
  if (response.status === 404) {
    throw new Error(
      'No downloadable files found. PDF files may be missing from storage. ' +
      'Try running a new crawl to re-download documents.'
    );
  }
  
  if (response.status !== 200) {
    throw new Error(`Download failed with status ${response.status}`);
  }
  
  const blob = new Blob([response.data], { type: 'application/zip' });
  
  // Check for empty ZIP (33 bytes = empty ZIP structure)
  if (blob.size < 100) {
    throw new Error(
      'Downloaded ZIP is empty. PDF files may be missing from storage. ' +
      'Try running a new crawl to re-download documents.'
    );
  }
  
  const contentDisposition = String(response.headers?.['content-disposition'] ?? '');
  const filename = extractFilename(
    contentDisposition,
    `policycheck_documents_${new Date().toISOString().slice(0, 10)}.zip`,
  );
  triggerBrowserDownload(blob, filename);
};

export const exportToCSV = (docs: Document[]): void => {
  const headers = ['ID', 'Insurer', 'Policy Type', 'Classification', 'Country', 'Confidence', 'Status', 'Source URL'];
  const rows = docs.map((doc) => [
    doc.id, doc.insurer, doc.policy_type, doc.classification, doc.country,
    `${((doc.confidence ?? 0) * 100).toFixed(0)}%`, doc.status, doc.source_url,
  ]);
  const csv = [
    headers.join(','),
    ...rows.map((row) => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(',')),
  ].join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const date = new Date().toISOString().slice(0, 10);
  triggerBrowserDownload(blob, `policycheck_export_${date}.csv`);
};

export const documentsApi = {
  uploadDocument: async (
    file: File,
    country: string = 'NZ',
    insurer?: string,
    policyType: string = 'General',
  ): Promise<Document> => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('country', country);
    if (insurer) formData.append('insurer', insurer);
    formData.append('policy_type', policyType);

    const response = await client.post('/api/documents/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },

  getDocuments: async (filters: DocumentFilters = {}): Promise<DocumentListResponse> => {
    try {
      const params = new URLSearchParams();
      Object.entries(filters).forEach(([key, value]) => {
        if (value !== undefined && value !== null && value !== '') {
          params.append(key, value.toString());
        }
      });
      const response = await client.get('/api/documents', { params });
      const data = response.data || {};
      const docs = data.documents || [];
      const total = data.total || 0;
      const limit = data.limit || filters.limit || 20;
      return {
        ...EMPTY_RESPONSE,
        ...data,
        documents: docs,
        items: docs,
        total,
        pages: Math.ceil(total / limit) || 1,
        page: filters.page || 1,
        page_size: limit,
      };
    } catch {
      return EMPTY_RESPONSE;
    }
  },

  getDocument: async (documentId: number): Promise<Document> => {
    const response = await client.get<Document>(`/api/documents/${documentId}`);
    return response.data;
  },

  getFilterOptions: async (): Promise<FilterOptions> => {
    try {
      const response = await client.get<FilterOptions>('/api/documents/filters/options');
      return response.data;
    } catch {
      return { countries: [], insurers: [], policy_types: [], classifications: [], statuses: [] };
    }
  },

  approveDocument: async (documentId: number) => {
    const response = await client.put(`/api/documents/${documentId}/approve`);
    return response.data;
  },

  reclassifyDocument: async (documentId: number, classification: string) => {
    const response = await client.put(`/api/documents/${documentId}/reclassify`, { classification });
    return response.data;
  },

  deleteDocument: async (documentId: number): Promise<void> => {
    await client.delete(`/api/documents/${documentId}`);
  },

  archiveDocument: async (documentId: number) => {
    const response = await client.put(`/api/documents/${documentId}/archive`);
    return response.data;
  },

  downloadDocument,
  downloadAllDocuments,
  getDocumentDownloadUrl,
  exportToCSV,
};

export const listDocuments = documentsApi.getDocuments;
export const searchLibrary = documentsApi.getDocuments;
export const uploadDocument = documentsApi.uploadDocument;
export const approveDocument = documentsApi.approveDocument;
export const reclassifyDocument = documentsApi.reclassifyDocument;
export const archiveDocument = documentsApi.archiveDocument;
export const deleteDocument = documentsApi.deleteDocument;
export const getFilterOptions = documentsApi.getFilterOptions;
