/**
 * Audit log API functions.
 */
import client from './client';
import type { AuditLogEntry } from '../types';

export interface AuditLogFilters {
  user_id?: number;
  document_id?: number;
  action?: string;
  skip?: number;
  limit?: number;
}

export interface AuditLogListResponse {
  entries: AuditLogEntry[];
  total: number;
  page: number;
  page_size: number;
}

const EMPTY_RESPONSE: AuditLogListResponse = {
  entries: [],
  total: 0,
  page: 1,
  page_size: 50,
};

export const auditApi = {
  getAuditLog: async (filters: AuditLogFilters = {}): Promise<AuditLogListResponse> => {
    try {
      const params = new URLSearchParams();
      Object.entries(filters).forEach(([key, value]) => {
        if (value !== undefined && value !== null) {
          params.append(key, value.toString());
        }
      });
      const response = await client.get<AuditLogListResponse>('/api/audit-log', { params });
      return { ...EMPTY_RESPONSE, ...response.data };
    } catch {
      return EMPTY_RESPONSE;
    }
  },
};

export const getAuditLog = auditApi.getAuditLog;
