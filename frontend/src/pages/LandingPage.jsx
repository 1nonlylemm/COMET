import { useState } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  ArrowRight,
  BookOpenCheck,
  BrainCircuit,
  Lock,
  Moon,
  Network,
  ShieldAlert,
  Sun,
} from 'lucide-react'
import { BrandLogo } from '../components/BrandLogo'
import { LoginModal } from '../features/auth/components/LoginModal'
import { getUser, isAuthenticated } from '../lib/auth'
import { getReturnToFromLocation, resolvePostLoginRedirect } from '../lib/authRedirect'
import { ROUTES } from '../config/routes'
import { useBranding } from '../hooks/useBranding'
import { useTheme } from '../hooks/useTheme'

const MotionDiv = motion.div
const MotionH1 = motion.h1
const MotionP = motion.p

const fadeUp = (delay = 0) => ({
  initial: { opacity: 0, y: 12 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.45, delay, ease: [0.22, 1, 0.36, 1] },
})

// ─── Feature card definitions ─────────────────────────────────────────────────
const FEATURE_CARDS = [
  {
    icon: BrainCircuit,
    number: '01',
    accent: 'blue',
    title: 'Documentary Review',
    description:
      'Record files received through DMS or official channels, match them to project requirements, and keep reviewer findings, versions, and compliance decisions in one internal record.',
    tags: ['Documentary intake', 'Requirement matching', 'Reviewer findings', 'Version history'],
  },
  {
    icon: ShieldAlert,
    number: '02',
    accent: 'amber',
    title: 'Deadlines and Notices',
    description:
      'Track working-day deadlines, returned-for-revision items, reminders, and notice preparation before a requirement becomes a formal non-compliance case.',
    tags: ['Working-day timers', 'Revision tracking', 'Reminder letters', 'Notice records'],
  },
  {
    icon: Network,
    number: '03',
    accent: 'slate',
    title: 'Program and LGU Context',
    description:
      'Keep LGU, cluster, program, funding year, project, and requirement context visible so staff can review submissions without rebuilding spreadsheet status by hand.',
    tags: ['LGU and cluster', 'Program cycle', 'Funding year', 'Project requirements'],
  },
  {
    icon: BookOpenCheck,
    number: '04',
    accent: 'emerald',
    title: 'Monitoring and Handoff',
    description:
      'Connect approved documentary requirements with implementation-stage records, completion follow-up, and the regional Google Drive handoff trail.',
    tags: ['Completion follow-up', 'Regional handoff', 'Audit history'],
  },
]

const ACCENT_ICON = {
  blue: 'text-blue-700 dark:text-blue-300 bg-blue-50 dark:bg-blue-500/10 border-blue-200 dark:border-blue-500/30',
  amber: 'text-amber-700 dark:text-amber-200 bg-amber-50 dark:bg-amber-400/10 border-amber-200 dark:border-amber-400/30',
  slate: 'text-slate-700 dark:text-slate-200 bg-slate-100 dark:bg-slate-700/40 border-slate-200 dark:border-slate-600/60',
  emerald: 'text-emerald-700 dark:text-emerald-200 bg-emerald-50 dark:bg-emerald-400/10 border-emerald-200 dark:border-emerald-400/30',
}

// ─── Feature card ─────────────────────────────────────────────────────────────
function FeatureCard({ card, index }) {
  const { icon: Icon, number, title, description, tags, accent } = card
  return (
    <MotionDiv
      {...fadeUp(0.06 * index + 0.2)}
      className="group relative flex flex-col gap-4 rounded-lg border border-brand-border bg-brand-surface-solid p-5 shadow-sm transition-colors hover:border-slate-300 dark:hover:border-slate-600"
    >
      <div className="flex items-start justify-between">
        <div className={`inline-flex h-9 w-9 items-center justify-center rounded-md border ${ACCENT_ICON[accent]}`}>
          <Icon className="h-4 w-4" strokeWidth={2} />
        </div>
        <span className="font-display text-xs font-semibold tabular-nums tracking-wider text-brand-text-muted">
          {number}
        </span>
      </div>

      <div className="flex-1">
        <h3 className="mb-1.5 font-display text-[15px] font-semibold leading-snug text-brand-text">
          {title}
        </h3>
        <p className="text-sm leading-relaxed text-brand-text-muted">{description}</p>
      </div>

      {tags?.length > 0 && (
        <div className="flex flex-wrap gap-1.5 pt-1">
          {tags.map((tag) => (
            <span
              key={tag}
              className="rounded-md border border-brand-border bg-brand-surface px-2 py-0.5 text-[11px] font-medium text-brand-text-muted"
            >
              {tag}
            </span>
          ))}
        </div>
      )}
    </MotionDiv>
  )
}

// ─── Project record preview ───────────────────────────────────────────────────
function AppShellMockup() {
  const timeline = [
    {
      stage: 'Intake',
      label: 'Document intake logged',
      meta: 'Mar 04 · Annex C attached',
      tone: 'done',
    },
    {
      stage: 'Review',
      label: 'Requirement review complete',
      meta: 'Mar 11 · 2 deficiencies noted',
      tone: 'done',
    },
    {
      stage: 'Monitoring',
      label: 'QAAR site visit scheduled',
      meta: 'Apr 18 · working-day timer: 6d',
      tone: 'active',
    },
    {
      stage: 'Closeout',
      label: 'Regional handoff · dispatch',
      meta: 'Pending completion packet',
      tone: 'pending',
    },
  ]

  const toneStyles = {
    done: {
      rail: 'bg-emerald-500',
      ring: 'ring-emerald-500/20',
      dot: 'bg-emerald-500',
    },
    active: {
      rail: 'bg-blue-500',
      ring: 'ring-blue-500/25',
      dot: 'bg-blue-500',
    },
    pending: {
      rail: 'bg-slate-300 dark:bg-slate-600',
      ring: 'ring-slate-400/15',
      dot: 'bg-slate-300 dark:bg-slate-600',
    },
  }

  return (
    <div className="group relative mx-auto w-full max-w-md opacity-80 saturate-[0.85] transition-all duration-300 hover:opacity-100 hover:saturate-100 lg:ml-auto">
      <div className="overflow-hidden rounded-xl border border-brand-border bg-brand-surface-solid shadow-sm">
        {/* Window chrome */}
        <div className="flex h-8 items-center gap-1.5 border-b border-brand-border bg-slate-50/80 px-3 dark:bg-slate-900/60">
          <div className="h-2 w-2 rounded-full bg-slate-300 dark:bg-slate-600" />
          <div className="h-2 w-2 rounded-full bg-slate-300 dark:bg-slate-600" />
          <div className="h-2 w-2 rounded-full bg-slate-300 dark:bg-slate-600" />
          <div className="ml-3 inline-flex items-center gap-1.5 rounded border border-brand-border bg-white/70 px-2 py-0.5 text-[10px] font-medium text-brand-text-muted dark:bg-slate-900/60">
            <Lock className="h-2.5 w-2.5" />
            pdmu.workspace / projects / LGU-2025-0142
          </div>
        </div>

        {/* Record header */}
        <div className="border-b border-brand-border px-5 pb-4 pt-5">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="font-display text-[10px] font-semibold uppercase tracking-[0.14em] text-brand-text-muted">
                Project record · PY 2025
              </p>
              <h3 className="mt-1 font-display text-[15px] font-semibold leading-snug text-brand-text">
                Barangay Multi-Purpose Hall —{' '}
                <span className="text-brand-text-muted">San Pedro Cluster 2</span>
              </h3>
            </div>
            <span className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-blue-200 bg-blue-50 px-2 py-0.5 text-[10px] font-semibold text-blue-700 dark:border-blue-400/30 dark:bg-blue-400/10 dark:text-blue-200">
              <span className="h-1.5 w-1.5 rounded-full bg-blue-500" />
              In monitoring
            </span>
          </div>

          <dl className="mt-4 grid grid-cols-3 gap-3">
            {[
              { k: 'LGU', v: 'San Pedro' },
              { k: 'Funding year', v: 'FY 2025' },
              { k: 'Cycle', v: 'Q2 · Cycle 2' },
            ].map((f) => (
              <div key={f.k}>
                <dt className="text-[9.5px] font-semibold uppercase tracking-wider text-brand-text-muted">
                  {f.k}
                </dt>
                <dd className="mt-0.5 font-display text-[13px] font-semibold text-brand-text">
                  {f.v}
                </dd>
              </div>
            ))}
          </dl>
        </div>

        {/* Timeline */}
        <div className="px-5 py-4">
          <div className="mb-3 flex items-center justify-between">
            <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-brand-text-muted">
              Intake → Closeout
            </p>
            <span className="text-[10px] font-medium text-brand-text-muted">4 stages</span>
          </div>

          <ol className="relative space-y-3.5">
            {/* vertical rail */}
            <span
              aria-hidden="true"
              className="absolute left-[5px] top-1.5 bottom-1.5 w-px bg-brand-border"
            />

            {timeline.map((item) => {
              const tone = toneStyles[item.tone]
              return (
                <li key={item.label} className="relative flex items-start gap-3 pl-5">
                  <span
                    className={`absolute left-0 top-1 h-2.5 w-2.5 rounded-full ring-4 ${tone.dot} ${tone.ring}`}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline justify-between gap-2">
                      <p className="truncate text-[12.5px] font-semibold text-brand-text">
                        {item.label}
                      </p>
                      <span className="shrink-0 text-[10px] font-semibold uppercase tracking-wider text-brand-text-muted">
                        {item.stage}
                      </span>
                    </div>
                    <p className="mt-0.5 truncate text-[11px] text-brand-text-muted">
                      {item.meta}
                    </p>
                  </div>
                </li>
              )
            })}
          </ol>
        </div>

        {/* Footer strip */}
        <div className="flex items-center justify-between border-t border-brand-border bg-slate-50/60 px-5 py-2.5 dark:bg-slate-900/40">
          <div className="flex items-center gap-1.5 text-[10.5px] text-brand-text-muted">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
            Last updated 2h ago · RJ Mendoza
          </div>
          <div className="flex items-center gap-1 text-[10.5px] font-semibold text-brand-primary dark:text-blue-300">
            Open record
            <ArrowRight className="h-3 w-3" />
          </div>
        </div>
      </div>
    </div>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────
export default function LandingPage({ initialLoginOpen = false, onLogin }) {
  const { mode, setTheme } = useTheme()
  const { branding } = useBranding()
  const location = useLocation()
  const navigate = useNavigate()
  const [loginOpen, setLoginOpen] = useState(initialLoginOpen)
  const returnTo = getReturnToFromLocation(location)

  if (isAuthenticated()) {
    return <Navigate to={resolvePostLoginRedirect(getUser(), returnTo)} replace />
  }

  const toggleTheme = () => setTheme(mode === 'dark' ? 'light' : 'dark')
  const openLogin = () => setLoginOpen(true)
  const closeLogin = () => {
    setLoginOpen(false)
    if (location.pathname === ROUTES.LOGIN) {
      navigate(ROUTES.HOME, { replace: true })
    }
  }

  return (
    <div className="relative min-h-screen bg-background text-brand-text transition-colors duration-300 selection:bg-brand-primary/20">
      {/* Subtle grid background — hero region only */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 top-0 h-[560px] opacity-[0.35] dark:opacity-[0.18]"
        style={{
          backgroundImage:
            'linear-gradient(to right, var(--color-brand-border) 1px, transparent 1px), linear-gradient(to bottom, var(--color-brand-border) 1px, transparent 1px)',
          backgroundSize: '48px 48px',
          maskImage: 'radial-gradient(ellipse 70% 60% at 50% 0%, black 40%, transparent 100%)',
          WebkitMaskImage: 'radial-gradient(ellipse 70% 60% at 50% 0%, black 40%, transparent 100%)',
        }}
      />

      {/* Nav */}
      <nav className="fixed top-0 z-50 w-full border-b border-brand-border bg-background/85 backdrop-blur-md">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <BrandLogo size="md" nameClassName="text-base font-semibold tracking-tight" />
          <div className="flex items-center gap-1.5">
            <span className="hidden items-center gap-1.5 rounded-md border border-brand-border bg-brand-surface px-2.5 py-1 text-[11px] font-medium text-brand-text-muted sm:inline-flex">
              <Lock className="h-3 w-3" />
              Internal access
            </span>
            <button
              type="button"
              onClick={toggleTheme}
              className="rounded-md p-2 text-brand-text-muted transition-colors hover:bg-brand-surface hover:text-brand-text"
              aria-label="Toggle theme"
            >
              {mode === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </button>
            <button
              type="button"
              onClick={openLogin}
              className="rounded-md px-3 py-1.5 text-sm font-medium text-brand-text-muted transition-colors hover:bg-brand-surface hover:text-brand-text"
            >
              Sign in
            </button>
          </div>
        </div>
      </nav>

      <main className="relative">
        {/* Hero */}
        <section className="mx-auto max-w-6xl px-4 pb-16 pt-28 sm:px-6 lg:px-8 lg:pt-32">
          <div className="grid grid-cols-1 items-center gap-10 lg:grid-cols-[1.25fr_1fr] lg:gap-16">
            <div>
              <MotionDiv
                {...fadeUp(0)}
                className="mb-6 inline-flex items-center gap-2 rounded-full border border-brand-border bg-brand-surface-solid px-3 py-1 shadow-sm"
              >
                <span className="relative flex h-1.5 w-1.5">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-500 opacity-60" />
                  <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-500" />
                </span>
                <span className="text-[11px] font-semibold uppercase tracking-wider text-brand-text-muted">
                  {branding.app_tagline}
                </span>
              </MotionDiv>

              <MotionH1
                {...fadeUp(0.08)}
                className="font-display text-4xl font-bold leading-[1.1] tracking-tight text-brand-text sm:text-[44px] lg:text-5xl"
              >
                Project records,
                <br className="hidden sm:inline" />{' '}
                <span className="text-brand-primary dark:text-blue-300">
                  from intake to handoff.
                </span>
              </MotionH1>

              <MotionP
                {...fadeUp(0.16)}
                className="mt-5 max-w-xl text-[15px] leading-relaxed text-brand-text-muted"
              >
                {branding.app_name} is the internal workspace for DILG Laguna PDMU — recording, reviewing,
                tracking, and handing off LGU documentary requirement submissions across multiple programs.
              </MotionP>

              <MotionDiv {...fadeUp(0.22)} className="mt-8 flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  onClick={openLogin}
                  className="btn-primary inline-flex items-center gap-2 rounded-md px-5 py-2.5 text-sm"
                >
                  Sign in to workspace <ArrowRight className="h-4 w-4" />
                </button>
              </MotionDiv>

              {/* Inline operational signals */}
              <MotionDiv
                {...fadeUp(0.3)}
                className="mt-10 grid max-w-xl grid-cols-3 gap-3 border-t border-brand-border pt-6"
              >
                {[
                  { label: 'Documentary Requirements', value: 'Documentary Intake' },
                  { label: 'Review & Follow-up', value: 'Working-day deadlines' },
                  { label: 'Internal record trail', value: 'Review → handoff' },
                ].map((s) => (
                  <div key={s.label}>
                    <p className="font-display text-sm font-semibold text-brand-text">{s.value}</p>
                    <p className="mt-0.5 text-[11px] uppercase tracking-wider text-brand-text-muted">
                      {s.label}
                    </p>
                  </div>
                ))}
              </MotionDiv>
            </div>

            <MotionDiv {...fadeUp(0.15)} className="hidden lg:block">
              <AppShellMockup />
            </MotionDiv>
          </div>
        </section>

        {/* Features */}
        <section className="border-t border-brand-border bg-brand-surface/50 dark:bg-slate-900/30">
          <div className="mx-auto max-w-6xl px-4 py-20 sm:px-6 lg:px-8">
            <MotionDiv {...fadeUp(0)} className="mb-10 flex flex-col gap-4 sm:mb-12 sm:flex-row sm:items-end sm:justify-between">
              <div className="max-w-2xl">
                <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-brand-text-muted">
                  What the workspace supports
                </p>
                <h2 className="font-display text-2xl font-semibold leading-tight text-brand-text sm:text-3xl">
                  One internal record for each documentary compliance workflow.
                </h2>
              </div>
              <p className="max-w-sm text-sm leading-relaxed text-brand-text-muted">
                Documentary intake, requirement review, deadlines, notices, monitoring records, and regional handoff stay connected to the same project and LGU context.
              </p>
            </MotionDiv>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {FEATURE_CARDS.map((card, i) => (
                <FeatureCard key={card.title} card={card} index={i} />
              ))}
            </div>
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="border-t border-brand-border bg-background">
        <div className="mx-auto flex max-w-6xl flex-col items-start justify-between gap-3 px-4 py-8 sm:flex-row sm:items-center sm:px-6 lg:px-8">
          <BrandLogo size="sm" nameClassName="font-semibold text-brand-text-muted" />
          <p className="text-xs text-brand-text-muted">
            {branding.app_name} — internal system for DILG Laguna PDMU operations.
          </p>
        </div>
      </footer>

      <LoginModal open={loginOpen} onClose={closeLogin} onLogin={onLogin} returnTo={returnTo} />
    </div>
  )
}
