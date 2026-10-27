import { NavLink, useLocation } from 'react-router-dom'
import {
  Activity,
  Archive,
  BarChart3,
  BookOpen,
  Bot,
  Bell,
  LayoutDashboard,
  Users,
  Building2,
  FolderKanban,
  ClipboardList,
  ClipboardCheck,
  Clock,
  ShieldCheck,
  Inbox,
  ExternalLink,
  ChevronLeft,
  ChevronRight,
  LogOut,
  MapPinned,
  Moon,
  Settings,
  Sun,
  UserRound
} from 'lucide-react'
import { useTheme } from '../hooks/useTheme'
import { ROUTES } from '../config/routes'
import { BrandLogo } from './BrandLogo'

export function Sidebar({ user, onLogout, collapsed = false, mobileOpen = false, onMobileClose, onToggle }) {
  const { mode, setTheme } = useTheme()
  const location = useLocation()
  const isSystemAdmin = user?.role === 'system_admin'
  const isAdmin = user?.role === 'admin'
  const isStaff = user?.role === 'staff'
  const isInternalOps = isAdmin || isStaff
  const isFieldOfficer = user?.role === 'field_officer'
  const systemAdminSections = [
    {
      label: 'System Administration',
      items: [
        { to: ROUTES.SYSTEM_ADMIN, icon: LayoutDashboard, label: 'Overview', end: true },
        { to: ROUTES.SYSTEM_ADMIN_TECHNICAL_SETTINGS, icon: Settings, label: 'Technical Settings' },
        { to: ROUTES.USERS, icon: Users, label: 'Users' },
      ],
    },
    {
      label: 'System Operations',
      items: [
        { to: ROUTES.SYSTEM_ADMIN_DIAGNOSTICS, icon: Activity, label: 'Diagnostics' },
        { to: ROUTES.AI_ASSIST, icon: Bot, label: 'Assistant' },
        { to: ROUTES.AUDIT, icon: ShieldCheck, label: 'Audit Logs' },
      ],
    },
    {
      label: 'Account',
      items: [
        { to: ROUTES.ACCOUNT, icon: UserRound, label: 'Account' },
      ],
    },
  ]
  const fieldOfficerSections = [
    {
      label: 'Field Work',
      items: [
        { to: ROUTES.FIELD_WORK, icon: MapPinned, label: 'My Field Work', activePaths: [ROUTES.DASHBOARD, ROUTES.FIELD_WORK] },
        { to: ROUTES.INTAKE, icon: Inbox, label: 'Evidence Intake' },
        { to: ROUTES.NOTIFICATIONS, icon: Bell, label: 'Notifications' },
        { to: ROUTES.PROJECTS, icon: ClipboardList, label: 'Assigned Projects' },
        { to: ROUTES.MONITORING, icon: ClipboardCheck, label: 'Monitoring' },
        { to: ROUTES.COMPLETION, icon: ClipboardCheck, label: 'Completion' },
        { to: ROUTES.SLA, icon: Clock, label: 'Compliance Deadlines' },
      ],
    },
    {
      label: 'Reference',
      items: [
        { to: ROUTES.LGUS, icon: Building2, label: 'Assigned LGUs' },
        { to: ROUTES.ARCHIVE, icon: Archive, label: 'Archive & Communications' },
        { to: ROUTES.LIBRARY, icon: BookOpen, label: 'Reference Library' },
        { to: ROUTES.AI_ASSIST, icon: Bot, label: 'Assistant' },
      ],
    },
  ]
  const navSections = (isSystemAdmin ? systemAdminSections : isFieldOfficer ? fieldOfficerSections : [
    {
      label: 'Operations',
      items: [
        { to: ROUTES.DASHBOARD, icon: LayoutDashboard, label: 'Dashboard' },
        { to: ROUTES.NOTIFICATIONS, icon: Bell, label: 'Notifications' },
        { to: ROUTES.AI_ASSIST, icon: Bot, label: 'Assistant' },
        { to: ROUTES.INTAKE, icon: Inbox, label: 'Documentary Intake' },
        { to: ROUTES.PROJECTS, icon: ClipboardList, label: 'Projects' },
        { to: ROUTES.MONITORING, icon: ClipboardCheck, label: 'Monitoring' },
        ...(isInternalOps ? [{ to: ROUTES.REPORTS, icon: BarChart3, label: 'Reports & Analytics' }] : []),
        ...(isInternalOps ? [{ to: ROUTES.HANDOFF, icon: ExternalLink, label: 'Regional Handoff' }] : []),
        { to: ROUTES.COMPLETION, icon: ClipboardCheck, label: 'Completion' },
      ],
    },
    {
      label: 'Deadlines & Notices',
      items: [
        { to: ROUTES.SLA, icon: Clock, label: 'Compliance Deadlines' },
        ...(isInternalOps ? [{ to: ROUTES.ESCALATION, icon: ShieldCheck, label: 'Notices & Follow-Up' }] : []),
      ],
    },
    {
      label: 'Reference',
      items: [
        { to: ROUTES.PROGRAMS, icon: FolderKanban, label: 'Programs' },
        { to: ROUTES.LGUS, icon: Building2, label: 'LGUs' },
        { to: ROUTES.ARCHIVE, icon: Archive, label: 'Archive & Communications' },
        { to: ROUTES.LIBRARY, icon: BookOpen, label: 'Reference Library' },
        { to: ROUTES.ACCOUNT, icon: UserRound, label: 'Account' },
      ],
    },
    {
      label: 'Governance',
      items: [
        ...(isAdmin ? [{ to: ROUTES.CLUSTERS, icon: Building2, label: 'Clusters' }] : []),
        ...(isAdmin ? [{ to: ROUTES.USERS, icon: Users, label: 'Users' }] : []),
        ...(isAdmin ? [{ to: ROUTES.AUDIT, icon: ShieldCheck, label: 'Audit Log' }] : []),
        ...(isAdmin ? [{ to: ROUTES.SETTINGS, icon: Settings, label: 'Settings' }] : []),
      ],
    },
  ]).filter((section) => section.items.length > 0)

  const toggleTheme = () => {
    setTheme(mode === 'dark' ? 'light' : 'dark')
  }
  const showLabels = mobileOpen || !collapsed

  return (
    <>
    {mobileOpen && (
      <button
        type="button"
        className="fixed inset-0 z-40 bg-slate-950/40 lg:hidden"
        aria-label="Close navigation"
        onClick={onMobileClose}
      />
    )}
    <aside
      className={`fixed left-0 top-0 z-50 flex h-screen flex-col border-r border-brand-border
        bg-brand-surface-solid transition-transform duration-200 lg:z-40 lg:translate-x-0
        ${collapsed ? 'lg:w-16' : 'lg:w-64'} w-64 ${mobileOpen ? 'translate-x-0' : '-translate-x-full'}`}
    >
      <div className={`flex items-center justify-between border-b border-brand-border p-4 ${collapsed ? 'lg:justify-center' : ''}`}>
        {showLabels && (
          <BrandLogo nameClassName="text-lg font-bold text-slate-800 dark:text-white" />
        )}
        <div className="hidden lg:block">
        <button
          onClick={onToggle}
          className="icon-button min-h-8 min-w-8 p-1.5"
          aria-label={collapsed ? 'Expand navigation' : 'Collapse navigation'}
        >
          {collapsed ? <ChevronRight strokeWidth={1.5} className="h-4 w-4" /> : <ChevronLeft strokeWidth={1.5} className="h-4 w-4" />}
        </button>
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto py-4 px-2" aria-label="Main navigation">
        {navSections.map((section) => (
          <div key={section.label} className="mb-4">
            {showLabels && (
              <p className="micro-text px-3 mb-2">{section.label}</p>
            )}
            {section.items.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end ?? item.to === '/dashboard'}
                onClick={onMobileClose}
                aria-label={item.label}
                title={showLabels ? undefined : item.label}
                className={({ isActive }) => {
                  const isItemActive = isActive || item.activePaths?.includes(location.pathname)
                  return `mb-0.5 flex min-h-10 items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors
                  ${isItemActive
                    ? 'bg-brand-primary/10 text-brand-primary dark:bg-blue-600/20 dark:text-blue-100 font-medium'
                    : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800'
                  }
                  ${collapsed ? 'lg:justify-center' : ''}`
                }}
              >
                <item.icon strokeWidth={1.5} className="h-5 w-5 shrink-0" aria-hidden="true" />
                {showLabels && <span>{item.label}</span>}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>

      {user && (
        <div className="border-t border-brand-border p-3">
          {showLabels ? (
            <div className="flex items-center justify-between gap-2">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-slate-900 dark:text-white truncate">{user.first_name} {user.last_name}</p>
                <p className="text-xs text-slate-600 dark:text-slate-400 truncate">{user.email}</p>
              </div>
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={toggleTheme}
                  className="rounded-md p-1.5 text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-white"
                  title="Toggle theme"
                  aria-label="Toggle theme"
                >
                  {mode === 'dark' ? <Sun strokeWidth={1.5} className="h-4 w-4" aria-hidden="true" /> : <Moon strokeWidth={1.5} className="h-4 w-4" aria-hidden="true" />}
                </button>
                <button
                  type="button"
                  onClick={onLogout}
                  className="rounded-md p-1.5 text-slate-600 transition-colors hover:bg-red-100 hover:text-red-600 dark:text-slate-400 dark:hover:bg-red-500/20 dark:hover:text-red-300"
                  title="Sign out"
                  aria-label="Sign out"
                >
                  <LogOut strokeWidth={1.5} className="h-4 w-4" aria-hidden="true" />
                </button>
              </div>
            </div>
          ) : (
            <div className="flex flex-col items-center gap-2">
              <button
                type="button"
                onClick={toggleTheme}
                className="rounded-md p-2 text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-white"
                title="Toggle theme"
                aria-label="Toggle theme"
              >
                {mode === 'dark' ? <Sun strokeWidth={1.5} className="h-4 w-4" aria-hidden="true" /> : <Moon strokeWidth={1.5} className="h-4 w-4" aria-hidden="true" />}
              </button>
              <button
                type="button"
                onClick={onLogout}
                className="rounded-md p-2 text-slate-600 transition-colors hover:bg-red-100 hover:text-red-600 dark:text-slate-400 dark:hover:bg-red-500/20 dark:hover:text-red-300"
                title="Sign out"
                aria-label="Sign out"
              >
                <LogOut strokeWidth={1.5} className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>
          )}
        </div>
      )}
    </aside>
    </>
  )
}
