/**
 * TypeScript type definitions aligned with backend API responses.
 */

export interface User {
  id: number;
  username: string;
  name: string;
  role: 'admin' | 'reviewer';
  country: string;
  created_at?: string;
}

export interface Document {
  id: number;
  source_url: string;
  insurer: string;
  local_file_path: string;
  file_size?: number;
  file_hash?: string;
  country: string;
  policy_type: string;
  document_type: string;
  classification: string;
  confidence: number;
  status: string;
  metadata_json?: Record<string, unknown>;
  warnings?: string[];
  created_at: string;
  updated_at?: string;
}

/** Alias kept for backward compat in pages */
export type DocumentOut = Document & {
  file_name?: string;
  pdf_path?: string;
  crawl_id?: number;
  approved_by?: string;
  approved_at?: string;
};

export interface CrawlConfig {
  country: string;
  seed_urls: string[];
  policy_types: string[];
  keywords: string[];
  max_pages: number;
  max_time: number;
}

/** Matches backend CrawlResponse from POST /api/crawl */
export interface Crawl {
  crawl_id: number;
  status: string;
  message: string;
  active_crawls: number;
  max_concurrent_crawls: number;
}

/** Matches backend CrawlStatusResponse from GET /api/crawl/{id}/status */
export interface CrawlStatusResponse {
  id: number;
  status: string;
  country: string;
  progress_pct: number;
  pages_scanned: number;
  pdfs_found: number;
  pdfs_downloaded: number;
  pdfs_filtered: number;
  errors_count: number;
  max_pages?: number | null;
  current_phase?: string | null;
  phase_detail?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  seed_urls_crawled?: string[] | null;
  insurers_list?: string[] | null;
}

export interface AuditLogEntry {
  id: number;
  timestamp: string;
  user: string;
  user_name?: string;
  action: string;
  details?: Record<string, unknown>;
  document_id?: number;
  created_at: string;
}

export interface DashboardStats {
  total_documents: number;
  needs_review: number;
  auto_approved: number;
  user_approved: number;
  by_classification: Record<string, number>;
  by_country: Record<string, number>;
  recent_activity: AuditLogEntry[];
}

export interface PipelineStats {
  stages: Record<string, number>;
  funnel_rates: Record<string, number>;
  total_processed: number;
  avg_confidence: number;
  error_rate: number;
}

export interface ApiError {
  detail: string;
  error_type?: string;
  field?: string;
}
