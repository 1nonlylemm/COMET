import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Bell,
  Upload,
  FileEdit,
  Clock,
  ClipboardCheck,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Filter,
  Search,
  X,
  CheckCheck,
  ExternalLink,
} from 'lucide-react'
import { Button, GlassPanel, InlineAlert, PageHeader, ConfirmationModal, useToast, ErrorBoundary } from '../../../components'
import { ROUTES } from '../../../config/routes'
import api from '../../../lib/api'
import { formatDistanceToNow } from 'date-fns'
import { parseDate } from '../../../lib/formatters'

import { NOTIFICATION_CATEGORIES, getNotificationCategory } from '../../../lib/notificationPresentation'

const PRIORITY_CONFIG = {
  critical: {
    label: 'Critical',
    className: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300 border-red-300 dark:border-red-800',
  },
  high: {
    label: 'High',
    className: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300 border-amber-300 dark:border-amber-800',
  },
  normal: {
    label: 'Normal',
    className: 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300 border-blue-300 dark:border-blue-800',
  },
  low: {
    label: 'Low',
    className: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300 border-slate-300 dark:border-slate-700',
  },
}


function formatTimestamp(timestamp) {
  if (!timestamp) return ''
  try {
    const date = parseDate(timestamp)
    if (!date) return ''
    return formatDistanceToNow(date, { addSuffix: true })
  } catch {
    return ''
  }
}

function groupByDate(notifications) {
  const groups = {
    today: [],
    yesterday: [],
    thisWeek: [],
    older: [],
  }

  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const yesterday = new Date(today)
  yesterday.setDate(yesterday.getDate() - 1)
  const weekAgo = new Date(today)
  weekAgo.setDate(weekAgo.getDate() - 7)

  notifications.forEach((notification) => {
    const createdAt = parseDate(notification.created_at)
    if (!createdAt) {
      groups.older.push(notification)
      return
    }
    
    if (createdAt >= today) {
      groups.today.push(notification)
    } else if (createdAt >= yesterday) {
      groups.yesterday.push(notification)
    } else if (createdAt >= weekAgo) {
      groups.thisWeek.push(notification)
    } else {
      groups.older.push(notification)
    }
  })

  return groups
}

export default function NotificationsPage() {
  const navigate = useNavigate()
  const toast = useToast()
  const [notifications, setNotifications] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [searchTerm, setSearchTerm] = useState('')
  const [filterType, setFilterType] = useState('all')
  const [filterRead, setFilterRead] = useState('all')
  const [selectedIds, setSelectedIds] = useState([])
  const [isMarkingRead, setIsMarkingRead] = useState(false)
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(false)
  const LIMIT = 100

  const loadNotifications = useCallback(async (currentPage = page) => {
    setLoading(true)
    setError('')
    try {
      const response = await api.get('/notifications', {
        params: { include_read: true, limit: LIMIT, offset: (currentPage - 1) * LIMIT }
      })
      if (response.data?.success && response.data?.data) {
        const fetched = response.data.data.notifications || []
        setNotifications(fetched)
        setHasMore(fetched.length === LIMIT)
      }
    } catch (err) {
      setError(err.response?.data?.message || 'Unable to load notifications.')
    } finally {
      setLoading(false)
    }
  }, [page])

  useEffect(() => {
    loadNotifications(page)
  }, [loadNotifications, page])

  const filteredNotifications = useMemo(() => {
    let filtered = [...notifications]

    // Search filter
    if (searchTerm.trim()) {
      const term = searchTerm.toLowerCase()
      filtered = filtered.filter(n =>
        n.title?.toLowerCase().includes(term) ||
        n.message?.toLowerCase().includes(term)
      )
    }

    // Type filter
    if (filterType !== 'all') {
      filtered = filtered.filter(n => getNotificationCategory(n) === filterType)
    }

    // Read/Unread filter
    if (filterRead === 'unread') {
      filtered = filtered.filter(n => !n.is_read)
    } else if (filterRead === 'read') {
      filtered = filtered.filter(n => n.is_read)
    }

    return filtered
  }, [notifications, searchTerm, filterType, filterRead])

  const groupedNotifications = useMemo(() => {
    return groupByDate(filteredNotifications)
  }, [filteredNotifications])

  const unreadCount = notifications.filter(n => !n.is_read).length
  const selectedUnreadCount = notifications.filter(n => selectedIds.includes(n.id) && !n.is_read).length

  const hasActiveFilters = searchTerm || filterType !== 'all' || filterRead !== 'all'

  const clearFilters = () => {
    setSearchTerm('')
    setFilterType('all')
    setFilterRead('all')
  }

  const handleMarkAllRead = async () => {
    try {
      await api.put('/notifications/mark-read')
      setNotifications(prev => prev.map(n => ({ ...n, is_read: true })))
    } catch {
      setError('Failed to mark all as read.')
    }
  }

  const handleViewProject = (e, projectId) => {
    e.stopPropagation() // Prevent any parent click handlers
    if (projectId) {
      navigate(ROUTES.projectDetail(projectId))
    }
  }

  const handleBulkMarkRead = async () => {
    if (selectedIds.length === 0) return
    
    // Filter out already-read notifications
    const unreadSelected = notifications.filter(n => 
      selectedIds.includes(n.id) && !n.is_read
    )
    
    if (unreadSelected.length === 0) {
      toast.showToast({
        type: 'info',
        message: 'All selected notifications are already marked as read.',
        duration: 3000
      })
      return
    }
    
    setIsMarkingRead(true)
    try {
      await api.put('/notifications/mark-read', {
        notification_ids: selectedIds
      })
      
      // Update specific notifications to read
      setNotifications(prev => prev.map(n => 
        selectedIds.includes(n.id) ? { ...n, is_read: true } : n
      ))
      setSelectedIds([])
      
      toast.showToast({
        type: 'success',
        message: `Marked selected notifications as read`,
        duration: 3000
      })
    } catch {
      setError('Failed to mark notifications as read.')
    } finally {
      setIsMarkingRead(false)
    }
  }

  const toggleSelect = (id) => {
    setSelectedIds(prev =>
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
    )
  }

  const toggleSelectAll = () => {
    if (selectedIds.length === filteredNotifications.length) {
      setSelectedIds([])
    } else {
      setSelectedIds(filteredNotifications.map(n => n.id))
    }
  }

  const renderNotificationGroup = (title, items) => {
    if (items.length === 0) return null

    return (
      <div key={title} className="mb-8">
        <h3 className="mb-4 text-sm font-bold uppercase tracking-wide text-brand-text-muted">
          {title} ({items.length})
        </h3>
        <div className="space-y-2">
          {items.map((notification) => {
            const notifCategory = getNotificationCategory(notification)
            const typeConfig = NOTIFICATION_CATEGORIES[notifCategory] || NOTIFICATION_CATEGORIES.default
            const IconComponent = typeConfig.icon
            const isSelected = selectedIds.includes(notification.id)

            return (
              <GlassPanel
                key={notification.id}
                className={`group relative transition-all hover:shadow-md ${
                  !notification.is_read ? 'border-l-4 border-brand-primary bg-blue-50/30 dark:bg-blue-950/10' : ''
                } ${isSelected ? 'ring-2 ring-brand-primary' : ''}`}
              >
                <div className="flex items-start gap-4">
                  {/* Checkbox */}
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={(e) => {
                      e.stopPropagation()
                      toggleSelect(notification.id)
                    }}
                    onClick={(e) => e.stopPropagation()}
                    className="mt-1 h-4 w-4 rounded border-brand-border text-brand-primary focus:ring-brand-primary cursor-pointer"
                  />

                  {/* Icon */}
                  <div className={`flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-xl ${typeConfig.bgClass} border ${typeConfig.borderClass} transition-transform group-hover:scale-110`}>
                    <IconComponent className={`h-6 w-6 ${typeConfig.iconClass}`} strokeWidth={2} />
                  </div>

                  {/* Content */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-start justify-between gap-3 mb-2">
                      <div className="flex items-center gap-2">
                        <h4 className={`text-base leading-tight ${!notification.is_read ? 'font-bold text-brand-text' : 'font-semibold text-brand-text'}`}>
                          {notification.title}
                        </h4>
                        {!notification.is_read && (
                          <span className="flex h-2 w-2 rounded-full bg-brand-primary animate-pulse" />
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        {notification.priority && (
                          <span className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-bold border ${(PRIORITY_CONFIG[notification.priority] || PRIORITY_CONFIG.normal).className}`}>
                            {(PRIORITY_CONFIG[notification.priority] || PRIORITY_CONFIG.normal).label}
                          </span>
                        )}
                        <span className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-semibold ${typeConfig.bgClass} ${typeConfig.iconClass} border ${typeConfig.borderClass}`}>
                          {typeConfig.label}
                        </span>
                      </div>
                    </div>
                    {notification.message && (
                      <p className="mt-2 text-sm leading-relaxed text-brand-text-muted">
                        {notification.message}
                      </p>
                    )}
                    <div className="mt-3 flex items-center gap-4 text-xs text-brand-text-muted">
                      <span className="flex items-center gap-1.5">
                        <Clock className="h-3.5 w-3.5" strokeWidth={2} />
                        {formatTimestamp(notification.created_at)}
                      </span>
                      {notification.action_url ? (
                        <button
                          onClick={() => navigate(notification.action_url)}
                          className="flex items-center gap-1.5 text-brand-primary hover:text-brand-primary/80 hover:underline transition-colors font-medium cursor-pointer"
                        >
                          <ExternalLink className="h-3.5 w-3.5" strokeWidth={2} />
                          Open details
                        </button>
                      ) : notification.project_id ? (
                        <button
                          onClick={(e) => handleViewProject(e, notification.project_id)}
                          className="flex items-center gap-1.5 text-brand-primary hover:text-brand-primary/80 hover:underline transition-colors cursor-pointer"
                        >
                          <ExternalLink className="h-3.5 w-3.5" strokeWidth={2} />
                          View project
                        </button>
                      ) : null}
                    </div>
                  </div>
                </div>
              </GlassPanel>
            )
          })}
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Notifications"
        description="View and manage all your notifications in one place."
        actions={(
          <div className="flex flex-wrap items-center gap-2">
            {unreadCount > 0 && (
              <Button variant="outline" size="sm" icon={CheckCheck} onClick={handleMarkAllRead}>
                Mark all read ({unreadCount})
              </Button>
            )}
            <Button variant="outline" size="sm" icon={Bell} onClick={loadNotifications} disabled={loading}>
              Refresh
            </Button>
          </div>
        )}
      />

      <ErrorBoundary>
        <>
          {error && (
          <InlineAlert type="error" onDismiss={() => setError('')}>
            {error}
          </InlineAlert>
        )}

      {/* Stats */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-4">
        <GlassPanel className="text-center">
          <p className="text-3xl font-bold text-brand-text">{notifications.length}</p>
          <p className="mt-1 text-sm text-brand-text-muted">Total</p>
        </GlassPanel>
        <GlassPanel className="text-center">
          <p className="text-3xl font-bold text-blue-600 dark:text-blue-400">{unreadCount}</p>
          <p className="mt-1 text-sm text-brand-text-muted">Unread</p>
        </GlassPanel>
        <GlassPanel className="text-center">
          <p className="text-3xl font-bold text-green-700 dark:text-green-400">{notifications.length - unreadCount}</p>
          <p className="mt-1 text-sm text-brand-text-muted">Read</p>
        </GlassPanel>
        <GlassPanel className="text-center">
          <p className="text-3xl font-bold text-brand-primary">{filteredNotifications.length}</p>
          <p className="mt-1 text-sm text-brand-text-muted">Filtered</p>
        </GlassPanel>
      </div>

      {/* Filters */}
      <GlassPanel>
        <div className="space-y-4">
          {/* Search */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-brand-text-muted" />
            <input
              type="text"
              placeholder="Search notifications by title or message..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full rounded-lg border border-brand-border bg-brand-surface-solid py-3 pl-11 pr-10 text-sm text-brand-text placeholder-brand-text-muted focus:border-brand-primary focus:outline-none focus:ring-2 focus:ring-brand-primary/20"
            />
            {searchTerm && (
              <button
                onClick={() => setSearchTerm('')}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-brand-text-muted hover:text-brand-text"
              >
                <X className="h-5 w-5" />
              </button>
            )}
          </div>

          {/* Filter Controls */}
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2">
              <Filter className="h-4 w-4 text-brand-text-muted" />
              <select
                value={filterType}
                onChange={(e) => setFilterType(e.target.value)}
                className="rounded-md border border-brand-border bg-brand-surface-solid px-3 py-2 text-sm text-brand-text focus:border-brand-primary focus:outline-none focus:ring-1 focus:ring-brand-primary"
              >
                <option value="all">All Types</option>
                {Object.entries(NOTIFICATION_CATEGORIES).map(([key, config]) => (
                  <option key={key} value={key}>{config.label}</option>
                ))}
              </select>
            </div>

            <select
              value={filterRead}
              onChange={(e) => setFilterRead(e.target.value)}
              className="rounded-md border border-brand-border bg-brand-surface-solid px-3 py-2 text-sm text-brand-text focus:border-brand-primary focus:outline-none focus:ring-1 focus:ring-brand-primary"
            >
              <option value="all">All Status</option>
              <option value="unread">Unread Only</option>
              <option value="read">Read Only</option>
            </select>

            {selectedIds.length > 0 && (
              <div className="flex items-center gap-2 rounded-md bg-brand-primary/10 px-3 py-2">
                <span className="text-sm font-semibold text-brand-primary">
                  {selectedIds.length} selected
                </span>
                <button
                  onClick={() => setSelectedIds([])}
                  className="text-brand-primary hover:text-brand-primary/80"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            )}

            {hasActiveFilters && (
              <button
                onClick={clearFilters}
                className="inline-flex items-center gap-1.5 rounded-md bg-brand-primary/10 px-3 py-2 text-sm font-medium text-brand-primary hover:bg-brand-primary/20"
              >
                <X className="h-3.5 w-3.5" />
                Clear filters
              </button>
            )}

            <div className="ml-auto text-sm text-brand-text-muted">
              Showing <span className="font-semibold text-brand-text">{filteredNotifications.length}</span> of {notifications.length}
            </div>
          </div>

          {/* Bulk Actions */}
          {filteredNotifications.length > 0 && (
            <div className="flex items-center gap-3 border-t border-brand-border pt-4">
              <button
                onClick={toggleSelectAll}
                className="text-sm font-medium text-brand-primary hover:text-brand-primary/80"
              >
                {selectedIds.length === filteredNotifications.length ? 'Deselect all' : 'Select all'}
              </button>
              
              {selectedIds.length > 0 && (
                <>
                  <div className="h-4 w-px bg-brand-border" />
                  {selectedUnreadCount > 0 ? (
                    <button
                      onClick={handleBulkMarkRead}
                      disabled={isMarkingRead}
                      className="flex items-center gap-1.5 text-sm font-medium text-green-700 hover:text-green-800 dark:text-green-400 dark:hover:text-green-300 disabled:opacity-50"
                    >
                      <CheckCheck className="h-4 w-4" strokeWidth={2} />
                      {isMarkingRead ? 'Marking...' : `Mark selected as read (${selectedUnreadCount} unread)`}
                    </button>
                  ) : (
                    <span className="text-sm font-medium text-brand-text-muted">
                      All selected are already read
                    </span>
                  )}
                </>
              )}
            </div>
          )}
        </div>
      </GlassPanel>

      {/* Notifications List */}
      {loading ? (
        <div className="flex flex-col items-center justify-center py-16">
          <div className="h-12 w-12 animate-spin rounded-full border-4 border-brand-primary border-t-transparent" />
          <p className="mt-4 text-sm font-medium text-brand-text">Loading notifications...</p>
        </div>
      ) : filteredNotifications.length === 0 ? (
        <GlassPanel className="py-16 text-center">
          <div className="mx-auto mb-4 flex h-20 w-20 items-center justify-center rounded-full bg-slate-100 dark:bg-slate-800">
            <Bell className="h-10 w-10 text-slate-400" strokeWidth={2} />
          </div>
          <h3 className="text-lg font-bold text-brand-text">
            {hasActiveFilters ? 'No notifications match your filters' : 'No notifications yet'}
          </h3>
          <p className="mt-2 text-sm text-brand-text-muted">
            {hasActiveFilters ? 'Try adjusting your search or filters.' : 'You\'ll see notifications here as they arrive.'}
          </p>
          {hasActiveFilters && (
            <button
              onClick={clearFilters}
              className="mt-4 inline-flex items-center gap-2 rounded-md border border-brand-border bg-brand-surface-solid px-4 py-2 text-sm font-medium text-brand-text hover:bg-brand-surface"
            >
              Clear all filters
            </button>
          )}
        </GlassPanel>
      ) : (
        <div>
          {renderNotificationGroup('Today', groupedNotifications.today)}
          {renderNotificationGroup('Yesterday', groupedNotifications.yesterday)}
          {renderNotificationGroup('This Week', groupedNotifications.thisWeek)}
          {renderNotificationGroup('Older', groupedNotifications.older)}
          
          <div className="mt-8 flex items-center justify-between border-t border-brand-border pt-6 pb-4">
            <button
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page === 1 || loading}
              className="rounded-md border border-brand-border bg-brand-surface-solid px-4 py-2 text-sm font-medium text-brand-text hover:bg-brand-surface disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              Previous
            </button>
            <span className="text-sm font-medium text-brand-text-muted">
              Page {page}
            </span>
            <button
              onClick={() => setPage(p => p + 1)}
              disabled={!hasMore || loading}
              className="rounded-md border border-brand-border bg-brand-surface-solid px-4 py-2 text-sm font-medium text-brand-text hover:bg-brand-surface disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              Next
            </button>
          </div>
        </div>
      )}
      </>
    </ErrorBoundary>
    </div>
  )
}
