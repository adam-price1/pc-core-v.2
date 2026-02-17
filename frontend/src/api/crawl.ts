/**
 * Crawl API functions.
 */
import client from './client';
import type { Crawl, CrawlConfig, CrawlStatusResponse } from '../types';

export interface CrawlDeleteResponse {
  status: string;
  crawl_id: number;
  documents_deleted: number;
  files_deleted: number;
  message: string;
}

export const crawlApi = {
  startCrawl: async (config: CrawlConfig): Promise<Crawl> => {
    const response = await client.post<Crawl>('/api/crawl/start', config);
    return response.data;
  },

  getCrawlStatus: async (crawlId: number): Promise<CrawlStatusResponse> => {
    const response = await client.get<CrawlStatusResponse>(`/api/crawl/${crawlId}/status`);
    return response.data;
  },

  getCrawlResults: async (crawlId: number) => {
    const response = await client.get(`/api/crawl/${crawlId}/results`);
    return response.data;
  },

  deleteCrawl: async (crawlId: number): Promise<CrawlDeleteResponse> => {
    const response = await client.delete<CrawlDeleteResponse>(`/api/crawl/${crawlId}`);
    return response.data;
  },

  listSessions: async (limit = 100, offset = 0): Promise<CrawlStatusResponse[]> => {
    const response = await client.get<CrawlStatusResponse[]>('/api/crawl/sessions', {
      params: { limit, offset },
    });
    return response.data;
  },

  getActiveCount: async () => {
    const response = await client.get('/api/crawl/active/count');
    return response.data;
  },
};

export const startCrawl = crawlApi.startCrawl;
export const getCrawlStatus = crawlApi.getCrawlStatus;
export const deleteCrawl = crawlApi.deleteCrawl;
export const listCrawlSessions = crawlApi.listSessions;

// Custom insurer management
export async function addCustomInsurer(country: string, insurerName: string, seedUrls: string[], policyTypes?: string[]) {
  const res = await client.post('/api/crawl/custom-insurers', {
    country,
    insurer_name: insurerName,
    seed_urls: seedUrls,
    policy_types: policyTypes,
  });
  return res.data;
}

export async function removeCustomInsurer(country: string, insurerName: string) {
  const res = await client.delete(`/api/crawl/custom-insurers/${encodeURIComponent(country)}/${encodeURIComponent(insurerName)}`);
  return res.data;
}

export async function listCustomInsurers(country?: string) {
  const params = country ? { country } : {};
  const res = await client.get('/api/crawl/custom-insurers', { params });
  return res.data;
}
