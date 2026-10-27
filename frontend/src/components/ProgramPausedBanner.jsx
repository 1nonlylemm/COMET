import { Lock } from 'lucide-react'
import { Link } from 'react-router-dom'
import { ROUTES } from '../config/routes'
import { getUserRole } from '../lib/auth'

export function ProgramPausedBanner({ programId, role, className = '', message = 'Paused — program is inactive.' }) {
  const currentRole = role || getUserRole()
  const canManageProgram = currentRole === 'admin' || currentRole === 'staff' || currentRole === 'system_admin'

  return (
    <div
      data-testid="program-paused-banner"
      className={`inline-flex items-center gap-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs font-medium text-amber-900 shadow-sm dark:border-amber-700/60 dark:bg-amber-950/40 dark:text-amber-200 ${className}`}
      role="alert"
    >
      <Lock className="h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" aria-hidden="true" />
      <span>{message}</span>
      {canManageProgram && programId && (
        <Link
          to={ROUTES.programDetail(programId)}
          className="ml-1 font-semibold text-amber-800 underline underline-offset-2 hover:text-amber-950 dark:text-amber-300 dark:hover:text-amber-100"
        >
          Go to Program &rarr;
        </Link>
      )}
    </div>
  )
}
