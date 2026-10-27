import React from 'react'
import { AlertCircle, RefreshCw } from 'lucide-react'
import { GlassPanel } from './GlassPanel'

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  componentDidCatch(error, errorInfo) {
    if (this.props.onError) {
      try {
        this.props.onError(error, errorInfo)
      } catch {
        // Safe logging fallback
      }
    }
    console.error('ErrorBoundary caught an error:', error, errorInfo)
  }

  componentDidUpdate(prevProps) {
    if (this.state.hasError && this.props.resetKeys) {
      const prevKeys = prevProps.resetKeys || []
      const currentKeys = this.props.resetKeys || []
      const hasChanged =
        currentKeys.length !== prevKeys.length ||
        currentKeys.some((key, idx) => key !== prevKeys[idx])
      if (hasChanged) {
        this.handleReset()
      }
    }
  }

  handleReset = () => {
    if (this.props.onReset) {
      try {
        this.props.onReset(this.state.error)
      } catch {
        // Prevent onReset error from breaking boundary reset
      }
    }
    this.setState({ hasError: false, error: null })
  }

  render() {
    if (this.state.hasError) {
      if (typeof this.props.fallback === 'function') {
        return this.props.fallback({
          error: this.state.error,
          resetErrorBoundary: this.handleReset,
        })
      }

      if (this.props.fallback) {
        return this.props.fallback
      }

      if (this.props.compact) {
        return (
          <div
            role="alert"
            className="inline-flex items-center gap-2 rounded-lg border border-brand-border bg-brand-surface px-3 py-1.5 text-xs text-brand-text-muted shadow-sm"
          >
            <AlertCircle className="h-3.5 w-3.5 shrink-0 text-amber-500" aria-hidden="true" />
            <span className="truncate">{this.props.title || 'Component unavailable'}</span>
            <button
              type="button"
              onClick={this.handleReset}
              className="ml-1 inline-flex items-center gap-1 rounded font-medium text-brand-primary hover:underline"
              aria-label="Retry"
            >
              <RefreshCw className="h-3 w-3" />
              Retry
            </button>
          </div>
        )
      }

      return (
        <div className="mx-auto w-full max-w-4xl p-4 sm:p-6 lg:p-8" role="alert">
          <GlassPanel className="border-l-4 border-red-500 bg-red-50/10 py-12 text-center dark:bg-red-950/10">
            <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-full bg-red-100 dark:bg-red-900/30">
              <AlertCircle className="h-8 w-8 text-red-600 dark:text-red-400" />
            </div>
            <h2 className="mb-2 text-xl font-bold text-brand-text">
              {this.props.title || 'Something went wrong'}
            </h2>
            <p className="mx-auto mb-6 max-w-md text-brand-text-muted">
              {this.props.description ||
                'We encountered an unexpected error while loading this section. Please try refreshing the page.'}
            </p>
            <div className="flex flex-wrap items-center justify-center gap-3">
              <button
                type="button"
                onClick={this.handleReset}
                className="inline-flex items-center gap-2 rounded-md bg-brand-primary px-4 py-2 font-semibold text-white shadow-md transition-colors hover:bg-brand-primary/90 hover:shadow-lg dark:text-slate-950"
              >
                <RefreshCw className="h-4 w-4" />
                Try Again
              </button>
              <button
                type="button"
                onClick={() => window.location.reload()}
                className="inline-flex items-center gap-2 rounded-md border border-brand-border bg-brand-surface px-4 py-2 font-semibold text-brand-text transition-colors hover:bg-brand-surface-hover"
              >
                <RefreshCw className="h-4 w-4" />
                Refresh Page
              </button>
            </div>
          </GlassPanel>
        </div>
      )
    }

    return this.props.children
  }
}

export default ErrorBoundary
