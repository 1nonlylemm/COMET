import { Link, useLocation, useNavigate } from 'react-router-dom'
import {
  AlertTriangle,
  ArrowLeft,
  Home,
  LockKeyhole,
  RouteOff,
  ServerCrash,
  ShieldAlert,
} from 'lucide-react'
import { BrandLogo } from '../components/BrandLogo'
import { ROUTES } from '../config/routes'
import { getUser, isAuthenticated } from '../lib/auth'
import { getReturnToFromLocation, loginPath } from '../lib/authRedirect'
import { useBranding } from '../hooks/useBranding'

const getErrorContent = (appName = 'Workspace') => ({
  401: {
    icon: LockKeyhole,
    eyebrow: 'Session required',
    title: 'Sign in to continue.',
    description: `This workspace is limited to authorized ${appName} users. Sign in again to continue your work.`,
    detail: 'If your session expired, no records were changed.',
    tone: 'warning',
  },
  403: {
    icon: ShieldAlert,
    eyebrow: 'Access limited',
    title: 'This workspace area is not available for your role.',
    description: `Your account is active, but this page is reserved for another ${appName} role or permission group.`,
    detail: 'Use the navigation items available to your account, or ask an administrator to review your assignment.',
    tone: 'danger',
  },
  404: {
    icon: RouteOff,
    eyebrow: 'Page not found',
    title: `We could not find that ${appName} page.`,
    description: 'The route may have moved, the record may no longer exist, or the address may have been typed incorrectly.',
    detail: 'Return to a known workspace entry point and continue from the current queue.',
    tone: 'info',
  },
  405: {
    icon: AlertTriangle,
    eyebrow: 'Unsupported action',
    title: 'That action is not available from this screen.',
    description: `${appName} could not complete the requested action with the current method or context.`,
    detail: 'Refresh the page and use the visible workflow controls for this record.',
    tone: 'warning',
  },
  500: {
    icon: ServerCrash,
    eyebrow: 'System issue',
    title: `${appName} could not finish loading this screen.`,
    description: 'The workspace encountered a system issue before the page could complete.',
    detail: 'Try refreshing. If this continues, share the time and page with the system administrator.',
    tone: 'danger',
  },
})

const toneClasses = {
  danger: 'border-red-300 bg-red-50 text-red-700 dark:border-red-400/40 dark:bg-red-400/10 dark:text-red-200',
  info: 'border-blue-300 bg-blue-50 text-blue-700 dark:border-blue-400/40 dark:bg-blue-400/10 dark:text-blue-200',
  warning: 'border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-300/40 dark:bg-amber-300/10 dark:text-amber-100',
}

function primaryAction(statusCode, signedIn, returnTo) {
  if (statusCode === '401') {
    return { label: 'Sign in', to: loginPath(returnTo) }
  }
  return { label: signedIn ? 'Go to dashboard' : 'Go to home page', to: signedIn ? ROUTES.DASHBOARD : ROUTES.HOME }
}

export default function ErrorPage({
  statusCode = '404',
  title,
  description,
  detail,
  embedded = false,
}) {
  const navigate = useNavigate()
  const location = useLocation()
  const { branding } = useBranding()
  const signedIn = isAuthenticated()
  const user = getUser()
  const errorContentMap = getErrorContent(branding.app_name)
  const content = errorContentMap[String(statusCode)] || errorContentMap[404]
  const Icon = content.icon
  const returnTo = getReturnToFromLocation(location)
  const action = primaryAction(String(statusCode), signedIn, returnTo)

  const page = (
    <section className="mx-auto flex w-full max-w-3xl flex-col gap-6">
      {!embedded && (
        <div className="flex items-center justify-between gap-4">
          <BrandLogo size="md" nameClassName="text-base font-semibold" />
          {user && (
            <p className="truncate text-right text-xs text-brand-text-muted">
              {user.first_name} {user.last_name}
            </p>
          )}
        </div>
      )}

      <div className="content-section overflow-hidden">
        <div className="border-b border-brand-border bg-brand-surface px-5 py-4">
          <p className="micro-text">{content.eyebrow}</p>
        </div>
        <div className="grid gap-6 px-5 py-6 sm:grid-cols-[auto_minmax(0,1fr)] sm:px-6">
          <div className={`flex h-14 w-14 items-center justify-center rounded-lg border ${toneClasses[content.tone]}`}>
            <Icon strokeWidth={1.7} className="h-7 w-7" aria-hidden="true" />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-brand-text-muted">Error {statusCode}</p>
            <h1 className="mt-1 font-display text-2xl font-semibold text-brand-text">
              {title || content.title}
            </h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-brand-text-muted">
              {description || content.description}
            </p>
            <p className="mt-3 rounded-md border border-brand-border bg-brand-surface px-3 py-2 text-sm text-brand-text-muted">
              {detail || content.detail}
            </p>

            <div className="mt-6 flex flex-wrap items-center gap-2">
              <Link to={action.to} className="btn-primary inline-flex min-h-10 items-center gap-2">
                <Home strokeWidth={1.7} className="h-4 w-4" aria-hidden="true" />
                {action.label}
              </Link>
              <button
                type="button"
                onClick={() => navigate(-1)}
                className="btn-outline inline-flex min-h-10 items-center gap-2"
              >
                <ArrowLeft strokeWidth={1.7} className="h-4 w-4" aria-hidden="true" />
                Back
              </button>
            </div>
          </div>
        </div>
      </div>

      <p className="text-xs leading-5 text-brand-text-muted">
        {branding.app_name} keeps access decisions tied to your assigned role and LGU or cluster scope.
      </p>
    </section>
  )

  if (embedded) {
    return <div className="py-6">{page}</div>
  }

  return (
    <main className="flex min-h-screen items-center bg-background px-4 py-10 text-brand-text sm:px-6">
      {page}
    </main>
  )
}
