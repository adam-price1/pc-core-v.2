/**
 * Axios client with authentication interceptors.
 * Uses relative URLs — nginx proxies /api/ to the backend container.
 * In dev (vite), the vite proxy handles it.
 */
import axios, { AxiosError, InternalAxiosRequestConfig, AxiosResponse } from 'axios';
import { publishToast } from '../lib/toastBus';

// In production (Docker/nginx), use empty string so requests go to same origin.
// In dev (vite), vite.config proxy forwards /api to localhost:8000.
const API_URL = import.meta.env.VITE_API_URL || '';
const MUTATING_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);
const ERROR_TOAST_DEDUP_WINDOW_MS = 3000;

let lastToastKey = '';
let lastToastAt = 0;

function extractErrorMessage(error: AxiosError): string {
  const responseData = error.response?.data;

  if (typeof responseData === 'string' && responseData.trim()) {
    return responseData;
  }

  if (
    responseData &&
    typeof responseData === 'object' &&
    'detail' in (responseData as Record<string, unknown>)
  ) {
    const detail = (responseData as Record<string, unknown>).detail;
    if (typeof detail === 'string' && detail.trim()) {
      return detail;
    }
  }

  if (error.message?.trim()) {
    return error.message;
  }

  return 'Unexpected network error. Please try again.';
}

function publishErrorToast(error: AxiosError): void {
  const message = extractErrorMessage(error);
  const status = error.response?.status ?? 'network';
  const key = `${status}:${message}`;
  const now = Date.now();

  if (key === lastToastKey && now - lastToastAt < ERROR_TOAST_DEDUP_WINDOW_MS) {
    return;
  }

  lastToastKey = key;
  lastToastAt = now;
  publishToast({ message, type: 'error' });
}

const client = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor to add auth token
client.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = localStorage.getItem('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }

    const method = (config.method || 'GET').toUpperCase();
    if (MUTATING_METHODS.has(method)) {
      const csrfToken = localStorage.getItem('csrf_token');
      if (csrfToken) {
        config.headers['x-csrf-token'] = csrfToken;
      }
    }

    return config;
  },
  (error: AxiosError) => Promise.reject(error)
);

// Response interceptor for error handling
client.interceptors.response.use(
  (response: AxiosResponse) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      publishToast({ message: 'Session expired. Please log in again.', type: 'warning' });
      localStorage.removeItem('access_token');
      localStorage.removeItem('csrf_token');
      localStorage.removeItem('user');
      // Only redirect if not already on login page
      if (!window.location.pathname.startsWith('/login')) {
        window.location.href = '/login';
      }
      return Promise.reject(error);
    }

    if (error.code !== 'ERR_CANCELED') {
      publishErrorToast(error);
    }

    return Promise.reject(error);
  }
);

export default client;
