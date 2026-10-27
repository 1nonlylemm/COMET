import { createContext, useContext } from 'react'

export const FeedbackContext = createContext(null)

export function useToast() {
  const context = useContext(FeedbackContext)
  if (!context) {
    throw new Error('useToast must be used inside ToastProvider.')
  }
  return context
}
