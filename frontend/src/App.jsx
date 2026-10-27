import { lazy, Suspense, useEffect, useState } from 'react'
import { Routes, Route, Navigate, useLocation, useParams } from 'react-router-dom'
import { PageLayout } from './layouts/AdminLayout'
import { isAuthenticated, getUser, clearAuthData } from './lib/auth'
import { currentPathFromLocation, unauthorizedPath } from './lib/authRedirect'
import { ROUTES } from './config/routes'
import { useBranding } from './hooks/useBranding'
import { FiscalYearProvider } from './context/FiscalYearContext.jsx'
import api from './lib/api'
import ErrorBoundary from './components/ErrorBoundary'

const LandingPage = lazy(() => import('./pages/LandingPage'))
const LoginPage = lazy(() => import('./features/auth/pages/LoginPage'))
const ResetPasswordPage = lazy(() => import('./features/auth/pages/ResetPasswordPage'))
const ErrorPage = lazy(() => import('./pages/ErrorPage'))
const PasswordChangePage = lazy(() => import('./features/auth/components/PasswordChangePage'))
const MagicLinkChecklistPage = lazy(() => import('./features/magic-links/pages/MagicLinkChecklistPage'))
const AiAssistantPage = lazy(() => import('./features/ai/pages/AiAssistantPage'))
const DashboardPage = lazy(() => import('./features/dashboard/pages/DashboardPage'))
const FieldOfficerDashboardPage = lazy(() => import('./features/field/pages/FieldOfficerDashboardPage'))
const AccountSettingsPage = lazy(() => import('./features/account/pages/AccountSettingsPage'))
const AuditLogPage = lazy(() => import('./features/audit/pages/AuditLogPage'))
const CompletionPage = lazy(() => import('./features/completion/pages/CompletionPage'))
const EscalationPage = lazy(() => import('./features/escalation/pages/EscalationPage'))
const ArchiveCommunicationsPage = lazy(() => import('./features/governance/pages/ArchiveCommunicationsPage'))
const ReferenceLibraryPage = lazy(() => import('./features/library/pages/ReferenceLibraryPage'))
const RegionalHandoffPage = lazy(() => import('./features/handoff/pages/RegionalHandoffPage'))
const WorkbookImportPage = lazy(() => import('./features/imports/pages/WorkbookImportPage'))
const WorkbookWorkspacePage = lazy(() => import('./features/workbooks/pages/WorkbookWorkspacePage'))
const IntakeTriagePage = lazy(() => import('./features/intake/pages/IntakeTriagePage'))
const ClustersPage = lazy(() => import('./features/lgus/pages/ClustersPage'))
const LgusPage = lazy(() => import('./features/lgus/pages/LgusPage'))
const LguDetailPage = lazy(() => import('./features/lgus/pages/LguDetailPage'))
const ImplementationMonitoringPage = lazy(() => import('./features/monitoring/pages/ImplementationMonitoringPage'))
const ReportsAnalyticsPage = lazy(() => import('./features/reports/pages/ReportsAnalyticsPage'))
const CheckerAccuracyReportPage = lazy(() => import('./features/reports/pages/CheckerAccuracyReportPage'))
const ProgramListPage = lazy(() => import('./features/programs/pages/ProgramListPage'))
const ProgramDetailPage = lazy(() => import('./features/programs/pages/ProgramDetailPage'))
const ProjectListPage = lazy(() => import('./features/projects/pages/ProjectListPage'))
const ProjectDetailPage = lazy(() => import('./features/projects/pages/ProjectDetailPage'))
const SlaTrackerPage = lazy(() => import('./features/sla/pages/SlaTrackerPage'))
const SettingsPage = lazy(() => import('./features/settings/pages/SettingsPage'))
const SystemAdminOverviewPage = lazy(() => import('./features/system-admin/pages/SystemAdminOverviewPage'))
const SystemAdminTechnicalSettingsPage = lazy(() => import('./features/system-admin/pages/SystemAdminTechnicalSettingsPage'))
const SystemAdminDiagnosticsPage = lazy(() => import('./features/system-admin/pages/SystemAdminDiagnosticsPage'))
const UserManagementPage = lazy(() => import('./features/users/pages/UserManagementPage'))
const NotificationsPage = lazy(() => import('./features/notifications/pages/NotificationsPage'))

const ROLE_GROUPS = {
  operationalAdminOnly: ['admin'],
  systemAdminOnly: ['system_admin'],
  userGovernance: ['system_admin', 'admin'],
  internalOps: ['admin', 'staff'],
  fieldOnly: ['field_officer'],
  coreApp: ['admin', 'staff', 'field_officer'],
  assistant: ['admin', 'staff', 'field_officer', 'system_admin'],
}

function ProtectedRoute({ children, allowedRoles = null, embeddedError = false, redirectTo = null }) {
  const location = useLocation()
  const { branding } = useBranding()

  if (!isAuthenticated()) {
    const returnTo = currentPathFromLocation(location)
    return <Navigate to={unauthorizedPath(returnTo)} replace state={{ from: returnTo }} />
  }
  if (allowedRoles?.length) {
    const role = getUser()?.role
    if (!allowedRoles.includes(role)) {
      if (redirectTo) {
        return <Navigate to={redirectTo} replace />
      }
      return (
        <ErrorPage
          statusCode="403"
          embedded={embeddedError}
          detail={`This route is hidden from your navigation because it is outside your current ${branding.app_name} role permissions.`}
        />
      )
    }
  }
  return children
}

function ProtectedRedirect({ to, allowedRoles = null }) {
  return (
    <ProtectedRoute allowedRoles={allowedRoles}>
      <Navigate to={to} replace />
    </ProtectedRoute>
  )
}

function RoleRoute({ children, allowedRoles }) {
  return <ProtectedRoute allowedRoles={allowedRoles} embeddedError>{children}</ProtectedRoute>
}

function CoreAppRoute({ children }) {
  return <ProtectedRoute allowedRoles={ROLE_GROUPS.coreApp} redirectTo={ROUTES.DASHBOARD}>{children}</ProtectedRoute>
}

function LegacyProjectDetailRedirect() {
  const { id } = useParams()
  return <ProtectedRedirect to={ROUTES.projectDetail(id)} />
}

function LegacyProgramDetailRedirect() {
  const { id } = useParams()
  return <ProtectedRedirect to={ROUTES.programDetail(id)} />
}

function LegacyLguDetailRedirect() {
  const { id } = useParams()
  return <ProtectedRedirect to={ROUTES.lguDetail(id)} />
}

function RouteLoader({ children }) {
  const { branding } = useBranding()
  const location = useLocation()
  return (
    <ErrorBoundary resetKeys={[location.pathname]}>
      <Suspense
        fallback={
          <div className="flex min-h-screen items-center justify-center bg-background text-sm text-brand-text-muted">
            Loading {branding.app_name}...
          </div>
        }
      >
        {children}
      </Suspense>
    </ErrorBoundary>
  )
}

function App() {
  const [user, setUser] = useState(getUser())

  useEffect(() => {
    const handleUserRefresh = () => setUser(getUser())
    window.addEventListener('storage', handleUserRefresh)
    window.addEventListener('comet:user-updated', handleUserRefresh)
    return () => {
      window.removeEventListener('storage', handleUserRefresh)
      window.removeEventListener('comet:user-updated', handleUserRefresh)
    }
  }, [])

  const handleLogout = async () => {
    try {
      await api.post('/auth/logout')
    } catch {
      // Ignore network / token expiration errors during logout
    } finally {
      clearAuthData()
      setUser(null)
      window.location.href = ROUTES.LOGIN
    }
  }

  // 15-minute idle session timeout
  useEffect(() => {
    if (!user) return

    const IDLE_TIMEOUT_MS = 15 * 60 * 1000
    let timer = setTimeout(() => {
      handleLogout()
    }, IDLE_TIMEOUT_MS)

    const resetTimer = () => {
      clearTimeout(timer)
      timer = setTimeout(() => {
        handleLogout()
      }, IDLE_TIMEOUT_MS)
    }

    const events = ['mousedown', 'keydown', 'touchstart', 'scroll']
    events.forEach((evt) => window.addEventListener(evt, resetTimer, { passive: true }))

    return () => {
      clearTimeout(timer)
      events.forEach((evt) => window.removeEventListener(evt, resetTimer))
    }
  }, [user])

  return (
    <RouteLoader>
      <Routes>
        <Route path={ROUTES.HOME} element={<LandingPage onLogin={(u) => setUser(u)} />} />
        <Route path={ROUTES.LOGIN} element={<LoginPage onLogin={(u) => setUser(u)} />} />
        <Route path={ROUTES.RESET_PASSWORD} element={<ResetPasswordPage />} />
        <Route path={ROUTES.ERROR_401} element={<ErrorPage statusCode="401" />} />
        <Route path={ROUTES.ERROR_403} element={<ErrorPage statusCode="403" />} />
        <Route path={ROUTES.ERROR_404} element={<ErrorPage statusCode="404" />} />
        <Route path={ROUTES.ERROR_405} element={<ErrorPage statusCode="405" />} />
        <Route path={ROUTES.ERROR_500} element={<ErrorPage statusCode="500" />} />
        <Route path={ROUTES.MAGIC_LINK} element={<MagicLinkChecklistPage />} />

        <Route path="/projects" element={<ProtectedRedirect to={ROUTES.PROJECTS} />} />
        <Route path="/projects/:id" element={<LegacyProjectDetailRedirect />} />
        <Route path="/ai" element={<ProtectedRedirect to={ROUTES.AI_ASSIST} />} />
        <Route path="/field" element={<ProtectedRedirect to={ROUTES.FIELD_WORK} allowedRoles={ROLE_GROUPS.fieldOnly} />} />
        <Route path="/intake" element={<ProtectedRedirect to={ROUTES.INTAKE} />} />
        <Route path="/monitoring" element={<ProtectedRedirect to={ROUTES.MONITORING} />} />
        <Route path="/reports" element={<ProtectedRedirect to={ROUTES.REPORTS} allowedRoles={ROLE_GROUPS.internalOps} />} />
        <Route path="/handoff" element={<ProtectedRedirect to={ROUTES.HANDOFF} allowedRoles={ROLE_GROUPS.internalOps} />} />
        <Route path="/programs" element={<ProtectedRedirect to={ROUTES.PROGRAMS} />} />
        <Route path="/programs/:id" element={<LegacyProgramDetailRedirect />} />
        <Route path="/lgus" element={<ProtectedRedirect to={ROUTES.LGUS} />} />
        <Route path="/lgus/:id" element={<LegacyLguDetailRedirect />} />
        <Route path="/clusters" element={<ProtectedRedirect to={ROUTES.CLUSTERS} allowedRoles={ROLE_GROUPS.operationalAdminOnly} />} />
        <Route path="/sla" element={<ProtectedRedirect to={ROUTES.SLA} />} />
        <Route path="/completion" element={<ProtectedRedirect to={ROUTES.COMPLETION} />} />
        <Route path="/escalation" element={<ProtectedRedirect to={ROUTES.ESCALATION} allowedRoles={ROLE_GROUPS.internalOps} />} />
        <Route path="/users" element={<ProtectedRedirect to={ROUTES.USERS} allowedRoles={ROLE_GROUPS.userGovernance} />} />
        <Route path="/audit" element={<ProtectedRedirect to={ROUTES.AUDIT} allowedRoles={ROLE_GROUPS.userGovernance} />} />
        <Route path="/archive" element={<ProtectedRedirect to={ROUTES.ARCHIVE} />} />
        <Route path="/guidelines" element={<ProtectedRedirect to={ROUTES.GUIDELINES} />} />
        <Route path="/settings" element={<ProtectedRedirect to={ROUTES.SETTINGS} allowedRoles={ROLE_GROUPS.operationalAdminOnly} />} />
        <Route path="/system-admin" element={<ProtectedRedirect to={ROUTES.SYSTEM_ADMIN} allowedRoles={ROLE_GROUPS.systemAdminOnly} />} />
        <Route path="/system-admin/diagnostics" element={<ProtectedRedirect to={ROUTES.SYSTEM_ADMIN_DIAGNOSTICS} allowedRoles={ROLE_GROUPS.systemAdminOnly} />} />
        <Route path="/account" element={<ProtectedRedirect to={ROUTES.ACCOUNT} />} />

        <Route
          path={ROUTES.DASHBOARD}
          element={
            <ProtectedRoute>
              {user?.must_change_password ? (
                <PasswordChangePage user={user} onPasswordChanged={setUser} />
              ) : (
                <FiscalYearProvider>
                  <PageLayout user={user} onLogout={handleLogout} />
                </FiscalYearProvider>
              )}
            </ProtectedRoute>
          }
        >
          <Route index element={
            user?.role === 'field_officer'
              ? <FieldOfficerDashboardPage />
              : user?.role === 'system_admin'
                ? <Navigate to={ROUTES.SYSTEM_ADMIN} replace />
                : <DashboardPage />
          } />
          <Route path="ai" element={<RoleRoute allowedRoles={ROLE_GROUPS.assistant}><AiAssistantPage /></RoleRoute>} />
          <Route path="field" element={<RoleRoute allowedRoles={ROLE_GROUPS.fieldOnly}><FieldOfficerDashboardPage /></RoleRoute>} />
          <Route path="intake" element={<CoreAppRoute><IntakeTriagePage /></CoreAppRoute>} />
          <Route path="projects" element={<CoreAppRoute><ProjectListPage /></CoreAppRoute>} />
          <Route path="projects/:id" element={<CoreAppRoute><ProjectDetailPage /></CoreAppRoute>} />
          <Route path="monitoring" element={<CoreAppRoute><ImplementationMonitoringPage /></CoreAppRoute>} />
          <Route path="reports" element={<RoleRoute allowedRoles={ROLE_GROUPS.internalOps}><ReportsAnalyticsPage /></RoleRoute>} />
          <Route path="reports/checker-accuracy" element={<RoleRoute allowedRoles={ROLE_GROUPS.internalOps}><CheckerAccuracyReportPage /></RoleRoute>} />
          <Route path="handoff" element={<RoleRoute allowedRoles={ROLE_GROUPS.internalOps}><RegionalHandoffPage /></RoleRoute>} />
          <Route path="programs" element={<CoreAppRoute><ProgramListPage /></CoreAppRoute>} />
          <Route path="programs/:id" element={<CoreAppRoute><ProgramDetailPage /></CoreAppRoute>} />
          <Route path="programs/:programId/cycles/:cycleId/import" element={<RoleRoute allowedRoles={ROLE_GROUPS.operationalAdminOnly}><WorkbookImportPage /></RoleRoute>} />
          <Route path="programs/:programId/cycles/:cycleId/workbook" element={<RoleRoute allowedRoles={ROLE_GROUPS.internalOps}><WorkbookWorkspacePage /></RoleRoute>} />
          <Route path="lgus" element={<CoreAppRoute><LgusPage /></CoreAppRoute>} />
          <Route path="lgus/:id" element={<CoreAppRoute><LguDetailPage /></CoreAppRoute>} />
          <Route path="clusters" element={<RoleRoute allowedRoles={ROLE_GROUPS.operationalAdminOnly}><ClustersPage /></RoleRoute>} />
          <Route path="sla" element={<CoreAppRoute><SlaTrackerPage /></CoreAppRoute>} />
          <Route path="sla-tracker" element={<CoreAppRoute><SlaTrackerPage /></CoreAppRoute>} />
          <Route path="completion" element={<CoreAppRoute><CompletionPage /></CoreAppRoute>} />
          <Route path="escalation" element={<RoleRoute allowedRoles={ROLE_GROUPS.internalOps}><EscalationPage /></RoleRoute>} />
          <Route path="users" element={<RoleRoute allowedRoles={ROLE_GROUPS.userGovernance}><UserManagementPage /></RoleRoute>} />
          <Route path="users/new" element={<RoleRoute allowedRoles={ROLE_GROUPS.userGovernance}><UserManagementPage mode="create" /></RoleRoute>} />
          <Route path="users/:id" element={<RoleRoute allowedRoles={ROLE_GROUPS.userGovernance}><UserManagementPage mode="detail" /></RoleRoute>} />
          <Route path="audit" element={<RoleRoute allowedRoles={ROLE_GROUPS.userGovernance}><AuditLogPage /></RoleRoute>} />
          <Route path="archive" element={<CoreAppRoute><ArchiveCommunicationsPage /></CoreAppRoute>} />
          <Route path="guidelines" element={<CoreAppRoute><ReferenceLibraryPage /></CoreAppRoute>} />
          <Route path="library" element={<CoreAppRoute><ReferenceLibraryPage /></CoreAppRoute>} />
          <Route path="settings" element={<RoleRoute allowedRoles={ROLE_GROUPS.operationalAdminOnly}><SettingsPage /></RoleRoute>} />
          <Route path="system-admin" element={<RoleRoute allowedRoles={ROLE_GROUPS.systemAdminOnly}><SystemAdminOverviewPage /></RoleRoute>} />
          <Route path="system-admin/technical-settings" element={<RoleRoute allowedRoles={ROLE_GROUPS.systemAdminOnly}><SystemAdminTechnicalSettingsPage /></RoleRoute>} />
          <Route path="system-admin/diagnostics" element={<RoleRoute allowedRoles={ROLE_GROUPS.systemAdminOnly}><SystemAdminDiagnosticsPage /></RoleRoute>} />
          <Route path="account" element={<AccountSettingsPage />} />
          <Route path="notifications" element={<NotificationsPage />} />
          <Route path="*" element={<ErrorPage statusCode="404" embedded />} />
        </Route>

        <Route path="*" element={<ErrorPage statusCode="404" />} />
      </Routes>
    </RouteLoader>
  )
}

export default App
