/**
 * Stats API functions.
 */
import client from './client';
import type { PipelineStats, DashboardStats } from '../types';

const EMPTY_PIPELINE: PipelineStats = {
  stages: {},
  funnel_rates: {},
  total_processed: 0,
  avg_confidence: 0,
  error_rate: 0,
};

const EMPTY_DASHBOARD: DashboardStats = {
  total_documents: 0,
  needs_review: 0,
  auto_approved: 0,
  user_approved: 0,
  by_classification: {},
  by_country: {},
  recent_activity: [],
};

export const statsApi = {
  getPipelineStats: async (): Promise<PipelineStats> => {
    try {
      const response = await client.get<PipelineStats>('/api/stats/pipeline');
      return { ...EMPTY_PIPELINE, ...response.data };
    } catch {
      return EMPTY_PIPELINE;
    }
  },

  getDashboardStats: async (): Promise<DashboardStats> => {
    try {
      const response = await client.get<DashboardStats>('/api/stats/dashboard');
      return { ...EMPTY_DASHBOARD, ...response.data };
    } catch {
      return EMPTY_DASHBOARD;
    }
  },
};

export const getPipelineStats = statsApi.getPipelineStats;
export const getDashboardStats = statsApi.getDashboardStats;
