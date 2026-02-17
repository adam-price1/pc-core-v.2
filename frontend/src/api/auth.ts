/**
 * Authentication API functions.
 */
import client from './client';
import type { User } from '../types';

export interface LoginCredentials {
  username: string;
  password: string;
  country?: string;
}

export interface RegisterData {
  username: string;
  password: string;
  name: string;
  role?: string;
  country?: string;
}

export interface LoginResponse {
  access_token: string;
  csrf_token: string;
  token_type: string;
  user: User;
}

export const authApi = {
  login: async (credentials: LoginCredentials): Promise<LoginResponse> => {
    const response = await client.post<LoginResponse>('/api/auth/login', credentials);
    return response.data;
  },

  register: async (data: RegisterData): Promise<User> => {
    const response = await client.post<User>('/api/auth/register', data);
    return response.data;
  },
};

export const login = async (credentials: LoginCredentials): Promise<LoginResponse> => {
  return authApi.login(credentials);
};

export function register(data: RegisterData): Promise<User>;
export function register(username: string, password: string, name: string, country: string): Promise<User>;
export function register(
  usernameOrData: string | RegisterData,
  password?: string,
  name?: string,
  country?: string
): Promise<User> {
  if (typeof usernameOrData === 'string') {
    return authApi.register({
      username: usernameOrData,
      password: password!,
      name: name!,
      country: country,
    });
  }
  return authApi.register(usernameOrData);
}
