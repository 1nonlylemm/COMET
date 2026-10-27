import { useState, Suspense } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { AlertCircle, CalendarDays, Menu, RefreshCw } from 'lucide-react'
import { BrandLogo } from '../components/BrandLogo'
import { Sidebar } from '../components/Sidebar'
import { NotificationBell } from '../components/NotificationBell'
import { ROUTES } from '../config/routes'
import { AiAssistantDrawer } from '../features/ai/components/AiAssistantDrawer'
import { GlobalSearch } from '../features/search/components/GlobalSearch'
import { useFiscalYear } from '../context/useFiscalYear'
import { GlassPanel } from '../components/GlassPanel'
import ErrorBoundary from '../components/ErrorBoundary'

function normalizePath(pathname) {
  return pathname.replace(/\/+$/, '') || ROUTES.DASHBOARD
}



function getPageChromePolicy(pathname) {
  const isDashboardHome = pathname === ROUTES.DASHBOARD
  const isAiWorkspace = pathname === ROUTES.AI_ASSIST

  return {
    showAiDrawer: !isAiWorkspace,
    // Only show global search on the main dashboard overview, 
    // since specific queues and detail pages have local search.
    showGlobalSearch: isDashboardHome,
    showSystemFy: true, // Baseline behavior
  }
}

function RouteErrorFallback({ error, onReset }) {
  const navigate = useNavigate()
  return (
    <div className="mx-auto w-full max-w-3xl py-8" role="alert">
      <GlassPanel className="border-l-4 border-amber-500 bg-amber-50/10 p-6 sm:p-8 dark:bg-amber-950/10">
        <div className="flex items-start gap-4">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-amber-100 dark:bg-amber-900/30">
            <AlertCircle className="h-6 w-6 text-amber-600 dark:text-amber-400" />
          </div>
          <div className="min-w-0 flex-1">
            <h2 className="text-lg font-bold text-brand-text">Unable to display this view</h2>
            <p className="mt-1 text-sm text-brand-text-muted">
              This page encountered an unexpected rendering error. You can retry loading this page or switch to another section from the navigation menu.
            </p>
            {error?.message && (
              <p className="mt-3 rounded border border-brand-border bg-brand-surface/80 px-3 py-2 font-mono text-xs text-brand-text-muted">
                {error.message}
              </p>
            )}
            <div className="mt-5 flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={onReset}
                className="inline-flex items-center gap-2 rounded-md bg-brand-primary px-3.5 py-2 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-brand-primary/90 dark:text-slate-950"
              >
                <RefreshCw className="h-4 w-4" />
                Try Again
              </button>
              <button
                type="button"
                onClick={() => navigate(ROUTES.DASHBOARD)}
                className="inline-flex items-center gap-2 rounded-md border border-brand-border bg-brand-surface px-3.5 py-2 text-sm font-semibold text-brand-text shadow-sm transition-colors hover:bg-brand-surface-hover"
              >
                Return to Dashboard
              </button>
              <button
                type="button"
                onClick={() => window.location.reload()}
                className="inline-flex items-center gap-1.5 px-3 py-2 text-xs text-brand-text-muted hover:text-brand-text"
              >
                Reload Application
              </button>
            </div>
          </div>
        </div>
      </GlassPanel>
    </div>
  )
}

export function PageLayout({ user, onLogout }) {
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const { selectedFiscalYear, setSelectedFiscalYear, fiscalYearOptions, loading } = useFiscalYear()
  const location = useLocation()
  const normalizedPath = normalizePath(location.pathname)
  
  const { showAiDrawer, showGlobalSearch, showSystemFy } = getPageChromePolicy(normalizedPath)

  const renderFiscalYearSelector = () => (
    showSystemFy ? (
    <label className="flex min-h-11 items-center gap-2 rounded-lg border border-brand-border bg-brand-surface-solid px-3 text-sm text-brand-text shadow-sm">
      <CalendarDays strokeWidth={1.7} className="h-4 w-4 text-brand-text-muted" aria-hidden="true" />
      <span className="micro-text hidden sm:inline">System FY</span>
      <select
        value={selectedFiscalYear || ''}
        onChange={(event) => setSelectedFiscalYear(event.target.value)}
        disabled={loading || !fiscalYearOptions.length}
        className="min-h-9 bg-brand-surface-solid text-sm font-semibold text-brand-text outline-none cursor-pointer disabled:opacity-60 dark:bg-slate-900"
        aria-label="System fiscal year"
      >
        {!selectedFiscalYear && (
          <option value="" className="bg-white text-slate-900 dark:bg-slate-900 dark:text-slate-100">
            Loading...
          </option>
        )}
        {fiscalYearOptions.map((year) => (
          <option
            key={year}
            value={year}
            className="bg-white text-slate-900 dark:bg-slate-900 dark:text-slate-100"
          >
            {year}
          </option>
        ))}
      </select>
    </label>
    ) : null
  )

  return (
    <div className="min-h-screen aurora-bg">
      <Sidebar
        user={user}
        onLogout={onLogout}
        collapsed={collapsed}
        mobileOpen={mobileOpen}
        onMobileClose={() => setMobileOpen(false)}
        onToggle={() => setCollapsed((current) => !current)}
      />
      <main className={`min-h-screen p-4 pt-20 sm:p-6 sm:pt-20 lg:p-8 lg:pt-8 ${collapsed ? 'lg:ml-16' : 'lg:ml-64'}`}>
        <div className="fixed left-0 right-0 top-0 z-30 flex h-16 items-center justify-between gap-3 border-b border-brand-border bg-brand-surface-solid px-4 lg:hidden">
          <button
            type="button"
            onClick={() => setMobileOpen(true)}
            className="icon-button"
            aria-label="Open navigation"
          >
            <Menu strokeWidth={1.7} className="h-5 w-5" />
          </button>
          <div className="min-w-0 flex-1">
            <BrandLogo nameClassName="text-base" />
          </div>
          <div className="flex items-center gap-3">
            {(user?.role === 'staff' || user?.role === 'admin' || user?.role === 'field_officer') && (
              <ErrorBoundary compact title="Notifications unavailable">
                <NotificationBell />
              </ErrorBoundary>
            )}
            {renderFiscalYearSelector()}
          </div>
        </div>
        <div className="page-shell mb-4">
          <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center">
            {showGlobalSearch ? (
              <ErrorBoundary compact title="Search unavailable">
                <GlobalSearch />
              </ErrorBoundary>
            ) : (
              <div className="hidden lg:block" aria-hidden="true" />
            )}
            <div className="hidden lg:flex lg:items-center lg:gap-3">
              {(user?.role === 'staff' || user?.role === 'admin' || user?.role === 'field_officer') && (
                <ErrorBoundary compact title="Notifications unavailable">
                  <NotificationBell />
                </ErrorBoundary>
              )}
              {renderFiscalYearSelector()}
            </div>
          </div>
        </div>
        <div className="page-shell">
          <ErrorBoundary
            resetKeys={[location.pathname, selectedFiscalYear]}
            fallback={({ error, resetErrorBoundary }) => (
              <RouteErrorFallback error={error} onReset={resetErrorBoundary} />
            )}
          >
            <Suspense
              fallback={
                <div className="flex h-64 items-center justify-center text-sm text-brand-text-muted">
                  Loading content...
                </div>
              }
            >
              <Outlet key={selectedFiscalYear || 'fy-loading'} />
            </Suspense>
          </ErrorBoundary>
        </div>
      </main>
      {showAiDrawer && (
        <ErrorBoundary compact title="AI Assistant unavailable">
          <AiAssistantDrawer />
        </ErrorBoundary>
      )}
    </div>
  )
}
