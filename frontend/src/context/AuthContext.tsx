/**
 * Authentication context provider.
 */
import React, { createContext, useContext, useState, useEffect } from 'react';
import type { User } from '../types';
import { authApi, type LoginCredentials, type RegisterData } from '../api/auth';

interface AuthContextType {
  user: User | null;
  token: string | null;
  loading: boolean;
  isAuthenticated: boolean;
  isAdmin: boolean;
  login: (usernameOrCredentials: string | LoginCredentials, password?: string, country?: string) => Promise<void>;
  logout: () => void;
  register: (data: RegisterData) => Promise<User>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Load user and token from localStorage on mount
    const storedUser = localStorage.getItem('user');
    const storedToken = localStorage.getItem('access_token');
    if (storedUser) {
      setUser(JSON.parse(storedUser));
    }
    if (storedToken) {
      setToken(storedToken);
    }
    setLoading(false);
  }, []);

  const login = async (usernameOrCredentials: string | LoginCredentials, password?: string, country?: string) => {
    let credentials: LoginCredentials;
    if (typeof usernameOrCredentials === 'string') {
      credentials = {
        username: usernameOrCredentials,
        password: password!,
        country,
      };
    } else {
      credentials = usernameOrCredentials;
    }

    const response = await authApi.login(credentials);
    localStorage.setItem('access_token', response.access_token);
    localStorage.setItem('csrf_token', response.csrf_token);
    localStorage.setItem('user', JSON.stringify(response.user));
    setUser(response.user);
    setToken(response.access_token);
  };

  const logout = () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('csrf_token');
    localStorage.removeItem('user');
    setUser(null);
    setToken(null);
  };

  const register = async (data: RegisterData): Promise<User> => {
    const newUser = await authApi.register(data);
    return newUser;
  };

  const isAuthenticated = !!user && !!token;
  const isAdmin = user?.role === 'admin' || user?.role === 'reviewer';

  return (
    <AuthContext.Provider value={{ user, token, loading, isAuthenticated, isAdmin, login, logout, register }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
