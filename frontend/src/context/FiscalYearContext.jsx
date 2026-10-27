import { useCallback, useEffect, useMemo, useState } from 'react'
import * as programApi from '../features/programs/api/programApi'
import { getStoredFiscalYear, setStoredFiscalYear } from '../lib/fiscalYear'
import { FiscalYearContext } from './fiscalYearContext'

export function FiscalYearProvider({ children }) {
  const [selectedFiscalYear, setSelectedFiscalYearState] = useState(() => getStoredFiscalYear())
  const [fiscalYearOptions, setFiscalYearOptions] = useState([])
  const [defaultFiscalYear, setDefaultFiscalYear] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let isCurrent = true
    async function loadFiscalYears() {
      setLoading(true)
      setError('')
      try {
        const response = await programApi.listFiscalYears()
        if (!isCurrent) return
        const payload = response.data || {}
        const years = payload.years || []
        const fallbackYear = payload.default_fiscal_year || new Date().getFullYear()
        setFiscalYearOptions(years.length ? years : [fallbackYear])
        setDefaultFiscalYear(fallbackYear)
        setSelectedFiscalYearState((current) => {
          if (current && years.includes(current)) return current
          const next = current || fallbackYear
          setStoredFiscalYear(next)
          return next
        })
      } catch (err) {
        if (!isCurrent) return
        const fallbackYear = getStoredFiscalYear() || new Date().getFullYear()
        setFiscalYearOptions([fallbackYear])
        setDefaultFiscalYear(fallbackYear)
        setSelectedFiscalYearState(fallbackYear)
        setStoredFiscalYear(fallbackYear)
        setError(err.response?.data?.message || 'Fiscal year context could not be loaded.')
      } finally {
        if (isCurrent) setLoading(false)
      }
    }
    loadFiscalYears()
    return () => {
      isCurrent = false
    }
  }, [])

  const setSelectedFiscalYear = useCallback((value) => {
    const fiscalYear = Number(value)
    if (!Number.isInteger(fiscalYear)) return
    setStoredFiscalYear(fiscalYear)
    setSelectedFiscalYearState(fiscalYear)
  }, [])

  const value = useMemo(() => ({
    selectedFiscalYear,
    setSelectedFiscalYear,
    fiscalYearOptions,
    defaultFiscalYear,
    loading,
    error,
    isFiscalYearReady: !loading && Boolean(selectedFiscalYear),
  }), [defaultFiscalYear, error, fiscalYearOptions, loading, selectedFiscalYear, setSelectedFiscalYear])

  return (
    <FiscalYearContext.Provider value={value}>
      {children}
    </FiscalYearContext.Provider>
  )
}
