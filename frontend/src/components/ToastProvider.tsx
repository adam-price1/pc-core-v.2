import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { subscribeToasts, type ToastType } from '../lib/toastBus';

type ToastContextValue = {
  showToast: (message: string, type?: ToastType, durationMs?: number) => void;
};

type ToastItem = {
  id: string;
  message: string;
  type: ToastType;
};

const DEFAULT_DURATION_MS = 5000;

const STYLE_BY_TYPE: Record<ToastType, string> = {
  success: 'border-emerald-300 bg-emerald-600 text-white',
  error: 'border-red-300 bg-red-600 text-white',
  warning: 'border-amber-300 bg-amber-500 text-white',
  info: 'border-blue-300 bg-blue-600 text-white',
};

const ToastContext = createContext<ToastContextValue | undefined>(undefined);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((toast) => toast.id !== id));
  }, []);

  const showToast = useCallback(
    (message: string, type: ToastType = 'info', durationMs: number = DEFAULT_DURATION_MS) => {
      const id = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
      setToasts((prev) => [...prev, { id, message, type }]);
      window.setTimeout(() => removeToast(id), durationMs);
    },
    [removeToast],
  );

  useEffect(() => {
    return subscribeToasts((toast) => {
      showToast(toast.message, toast.type ?? 'info', toast.durationMs ?? DEFAULT_DURATION_MS);
    });
  }, [showToast]);

  const contextValue = useMemo(
    () => ({
      showToast,
    }),
    [showToast],
  );

  return (
    <ToastContext.Provider value={contextValue}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-full max-w-sm flex-col gap-2">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={`pointer-events-auto rounded-lg border px-4 py-3 text-sm shadow-lg ${STYLE_BY_TYPE[toast.type]}`}
            role="status"
            aria-live="polite"
          >
            {toast.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used inside ToastProvider');
  }
  return context;
}
