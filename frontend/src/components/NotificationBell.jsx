import { useState, useEffect, useRef } from 'react'
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
  ArrowRight,
} from 'lucide-react'
import { ROUTES } from '../config/routes'
import api from '../lib/api'
import { formatDistanceToNow } from 'date-fns'
import { parseDate } from '../lib/formatters'

import { NOTIFICATION_CATEGORIES, getNotificationCategory } from '../lib/notificationPresentation'


export function NotificationBell() {
  const navigate = useNavigate()
  const [isOpen, setIsOpen] = useState(false)
  const [notifications, setNotifications] = useState([])
  const [unreadCount, setUnreadCount] = useState(0)
  const [loading, setLoading] = useState(false)
  const dropdownRef = useRef(null)

  // Fetch unread count on mount and periodically
  useEffect(() => {
    fetchUnreadCount()
    const interval = setInterval(fetchUnreadCount, 30000) // Poll every 30 seconds
    return () => clearInterval(interval)
  }, [])

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false)
      }
    }

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside)
      return () => document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [isOpen])

  async function fetchUnreadCount() {
    try {
      const response = await api.get('/notifications/unread-count')
      if (response.data?.success && response.data?.data) {
        setUnreadCount(response.data.data.unread_count || 0)
      }
    } catch (error) {
      console.error('Failed to fetch unread count:', error)
    }
  }

  async function fetchNotifications() {
    setLoading(true)
    try {
      const response = await api.get('/notifications', {
        params: { include_read: true, limit: 9 } // Show max 9 in dropdown
      })
      if (response.data?.success && response.data?.data) {
        const fetched = response.data.data.notifications || []
        setNotifications(fetched)
        return fetched
      }
    } catch (err) {
      console.error('Failed to fetch notifications:', err)
    } finally {
      setLoading(false)
    }
    return []
  }

  async function markAllAsRead() {
    try {
      await api.put('/notifications/mark-read')
      setUnreadCount(0)
      // Update notifications to show as read using functional state update
      setNotifications(prev => prev.map(n => ({ ...n, is_read: true })))
    } catch (error) {
      console.error('Failed to mark notifications as read:', error)
    }
  }

  async function handleBellClick() {
    if (!isOpen) {
      // Opening dropdown - fetch notifications without marking as read
      setIsOpen(true)
      await fetchNotifications()
    } else {
      // Closing dropdown
      setIsOpen(false)
    }
  }

  async function handleNotificationClick(notification) {
    // Close dropdown
    setIsOpen(false)

    // Mark notification as read if unread
    if (!notification.is_read) {
      try {
        await api.put('/notifications/mark-read', { notification_ids: [notification.id] })
        setUnreadCount(prev => Math.max(0, prev - 1))
        setNotifications(prev => prev.map(n => n.id === notification.id ? { ...n, is_read: true } : n))
      } catch (error) {
        console.error('Failed to mark notification as read:', error)
      }
    }

    // Navigate to action_url if provided, else project detail if project_id exists
    if (notification.action_url) {
      navigate(notification.action_url)
    } else if (notification.project_id) {
      navigate(ROUTES.projectDetail(notification.project_id))
    }
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

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        type="button"
        onClick={handleBellClick}
        className="icon-button relative"
        aria-label={`Notifications${unreadCount > 0 ? ` (${unreadCount} unread)` : ''}`}
      >
        <Bell strokeWidth={1.7} className="h-5 w-5" />
        {unreadCount > 0 && (
          <span className="absolute -right-1 -top-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-brand-danger px-1 text-xs font-semibold text-white dark:text-slate-950">
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {isOpen && (
        <div className="absolute right-0 top-full z-50 mt-2 w-80 sm:w-96 rounded-lg border border-brand-border bg-brand-surface-solid shadow-xl">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-brand-border bg-gradient-to-r from-brand-surface to-brand-surface-solid px-5 py-4">
            <div className="flex items-center gap-2">
              <Bell className="h-5 w-5 text-brand-primary" strokeWidth={2} />
              <h3 className="text-base font-bold text-brand-text">Notifications</h3>
            </div>
            <div className="flex items-center gap-2">
              {(unreadCount > 0 || notifications.some(n => !n.is_read)) && (
                <button
                  type="button"
                  onClick={markAllAsRead}
                  className="text-xs font-semibold text-brand-primary hover:underline cursor-pointer"
                >
                  Mark all read
                </button>
              )}
              {notifications.length > 0 && (
                <span className="rounded-full bg-brand-primary/10 px-3 py-1 text-xs font-semibold text-brand-primary">
                  {notifications.length} recent
                </span>
              )}
            </div>
          </div>

          {/* Notifications List */}
          <div className="max-h-[500px] overflow-y-auto">
            {loading ? (
              <div className="flex flex-col items-center justify-center py-12">
                <div className="h-10 w-10 animate-spin rounded-full border-3 border-brand-primary border-t-transparent" />
                <p className="mt-3 text-sm font-medium text-brand-text">Loading notifications...</p>
              </div>
            ) : notifications.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12">
                <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-slate-100 dark:bg-slate-800">
                  <Bell strokeWidth={2} className="h-8 w-8 text-slate-400" />
                </div>
                <p className="text-base font-semibold text-brand-text">All caught up!</p>
                <p className="mt-1 text-sm text-brand-text-muted">No new notifications</p>
              </div>
            ) : (
              <ul className="divide-y divide-brand-border">
                {notifications.map((notification) => {
                  const notifCategory = getNotificationCategory(notification)
                  const typeConfig = NOTIFICATION_CATEGORIES[notifCategory] || NOTIFICATION_CATEGORIES.default
                  const IconComponent = typeConfig.icon

                  return (
                    <li
                      key={notification.id}
                      onClick={() => handleNotificationClick(notification)}
                      className={`group relative px-5 py-4 transition-all duration-200 hover:bg-brand-surface cursor-pointer ${
                        !notification.is_read ? 'bg-blue-50/50 dark:bg-blue-950/10 border-l-2 border-brand-primary' : ''
                      }`}
                    >
                      <div className="flex items-start gap-3">
                        {/* Icon */}
                        <div className={`flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg ${typeConfig.bgClass} border ${typeConfig.borderClass} transition-transform group-hover:scale-110`}>
                          <IconComponent className={`h-5 w-5 ${typeConfig.iconClass}`} strokeWidth={2} />
                        </div>

                        {/* Content */}
                        <div className="flex-1 min-w-0">
                          <div className="flex items-start justify-between gap-2 mb-1">
                            <p className={`text-sm leading-snug ${!notification.is_read ? 'font-bold text-brand-text' : 'font-semibold text-brand-text'}`}>
                              {notification.title}
                            </p>
                            {!notification.is_read && (
                              <span className="mt-1 h-2.5 w-2.5 flex-shrink-0 rounded-full bg-brand-primary animate-pulse" aria-label="Unread" />
                            )}
                          </div>
                          {notification.message && (
                            <p className="mt-1.5 text-sm leading-relaxed text-brand-text-muted line-clamp-2">
                              {notification.message}
                            </p>
                          )}
                          <p className="mt-2 flex items-center gap-1.5 text-xs font-medium text-brand-text-muted">
                            <Clock className="h-3.5 w-3.5" strokeWidth={2} />
                            {formatTimestamp(notification.created_at)}
                          </p>
                        </div>
                      </div>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>

          {/* Footer - View All Link */}
          {notifications.length > 0 && (
            <div className="border-t border-brand-border bg-brand-surface p-3">
              <button
                onClick={() => {
                  setIsOpen(false)
                  navigate(ROUTES.NOTIFICATIONS)
                }}
                className="flex w-full items-center justify-center gap-2 rounded-md bg-brand-primary/10 px-4 py-2.5 text-sm font-semibold text-brand-primary transition-all hover:bg-brand-primary/20 hover:shadow-sm"
              >
                View all notifications
                <ArrowRight className="h-4 w-4" strokeWidth={2} />
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
