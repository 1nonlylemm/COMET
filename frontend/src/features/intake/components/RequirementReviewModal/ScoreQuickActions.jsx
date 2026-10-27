import { ChevronDown, ShieldCheck, Sparkles } from 'lucide-react'
import { Button } from '../../../../components'

/**
 * ScoreQuickActions renders the Run Checker / Use Prior FY / Open Scorecard
 * quick action cluster next to the snapshot dial. It is stateless: every
 * loading flag and visibility toggle flows in via props.
 */
export function ScoreQuickActions({
  canRun,
  isCheckerRunning,
  isPriorRunning,
  hasPriorYearAvailable,
  hasScoreDetails,
  onRunChecker,
  onRunPriorYear,
  onOpenScorecard,
}) {
  if (!canRun) return null
  return (
    <div
      data-testid="score-quick-actions"
      className="flex flex-wrap items-center gap-2"
    >
      <Button
        size="sm"
        variant="outline"
        icon={ShieldCheck}
        loading={Boolean(isCheckerRunning)}
        onClick={onRunChecker}
      >
        Run Checker
      </Button>
      {hasPriorYearAvailable && (
        <Button
          size="sm"
          variant="outline"
          icon={Sparkles}
          loading={Boolean(isPriorRunning)}
          onClick={onRunPriorYear}
        >
          Use Prior FY
        </Button>
      )}
      {hasScoreDetails && (
        <Button
          size="sm"
          variant="ghost"
          icon={ChevronDown}
          onClick={onOpenScorecard}
        >
          Open Scorecard
        </Button>
      )}
    </div>
  )
}

export default ScoreQuickActions
