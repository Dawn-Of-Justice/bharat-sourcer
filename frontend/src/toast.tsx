import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { ToastContext, type ShowToast, type ToastTone } from './toastContext'

// Short-lived notices ("Share link copied", "Saved", errors) in one polite live region. Each toast closes after 3 s.
type Toast = { id: number; message: string; tone: ToastTone }

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const nextId = useRef(0)
  const show = useCallback<ShowToast>((message, tone = 'ok') => {
    const id = ++nextId.current
    // Keep at most three; a repeated message replaces its earlier copy.
    setToasts(current => [...current.filter(toast => toast.message !== message).slice(-2), { id, message, tone }])
  }, [])
  const dismiss = useCallback((id: number) => setToasts(current => current.filter(toast => toast.id !== id)), [])
  return (
    <ToastContext.Provider value={show}>
      {children}
      <div className="toast-region" role="status" aria-live="polite">
        {toasts.map(toast => (
          <ToastItem key={toast.id} toast={toast} onDone={dismiss} />
        ))}
      </div>
    </ToastContext.Provider>
  )
}

function ToastItem({ toast, onDone }: { toast: Toast; onDone: (id: number) => void }) {
  useEffect(() => {
    const timer = window.setTimeout(() => onDone(toast.id), 3000)
    return () => window.clearTimeout(timer)
  }, [toast.id, onDone])
  return (
    <div className={`toast toast-${toast.tone}`}>
      <span className="toast-icon" aria-hidden="true">
        {toast.tone === 'error' ? '!' : '✓'}
      </span>
      <span>{toast.message}</span>
      <button type="button" className="toast-close" aria-label="Dismiss" onClick={() => onDone(toast.id)}>
        ✕
      </button>
    </div>
  )
}
