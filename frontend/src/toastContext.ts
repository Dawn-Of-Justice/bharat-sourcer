import { createContext, useContext } from 'react'

export type ToastTone = 'ok' | 'error'
export type ShowToast = (message: string, tone?: ToastTone) => void

// Filled by ToastProvider (toast.tsx); outside it, toasts are silently dropped.
export const ToastContext = createContext<ShowToast>(() => undefined)
export const useToast = () => useContext(ToastContext)
