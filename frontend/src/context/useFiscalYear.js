import { useContext } from 'react'
import { FiscalYearContext } from './fiscalYearContext'

export function useFiscalYear() {
  const context = useContext(FiscalYearContext)
  if (!context) {
    throw new Error('useFiscalYear must be used inside FiscalYearProvider')
  }
  return context
}
