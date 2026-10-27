"""
Notification API Routes
Handles in-app notifications for staff and field officers
"""
from flask import request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.services import notification_service
from app.utils.auth import admin_or_staff_or_field_required
from app.utils.response import error_response, success_response

from . import notifications_bp


@notifications_bp.route('', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def get_notifications():
    """
    Get notifications for the current user.
    
    Query params:
        include_read: Include read notifications (default: false)
        limit: Maximum number of notifications (default: 50)
    
    Returns:
        {
            data: {
                notifications: [...],
                unread_count: int
            }
        }
    """
    try:
        user_id = get_jwt_identity()
        include_read = request.args.get('include_read', 'false').lower() == 'true'
        limit = request.args.get('limit', 50, type=int)
        
        # Limit the max to prevent abuse
        if limit > 100:
            limit = 100
        
        notifications = notification_service.get_user_notifications(
            user_id=user_id,
            include_read=include_read,
            limit=limit,
        )
        
        unread_count = notification_service.get_unread_count(user_id=user_id)
        
        return success_response(data={
            'notifications': notifications,
            'unread_count': unread_count,
        })
    except notification_service.NotificationError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@notifications_bp.route('/unread-count', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def get_unread_count():
    """
    Get count of unread notifications for the current user.
    
    Returns:
        {
            data: {
                unread_count: int
            }
        }
    """
    try:
        user_id = get_jwt_identity()
        unread_count = notification_service.get_unread_count(user_id=user_id)
        
        return success_response(data={
            'unread_count': unread_count,
        })
    except notification_service.NotificationError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@notifications_bp.route('/mark-read', methods=['PUT'])
@jwt_required()
@admin_or_staff_or_field_required
def mark_as_read():
    """
    Mark specific or all notifications as read for the current user.
    
    Accepts:
        { "notification_ids": [1, 2, 3] } (optional)
        
    Returns:
        {
            data: {
                marked_count: int
            },
            message: "X notifications marked as read"
        }
    """
    try:
        user_id = get_jwt_identity()
        data = request.get_json(silent=True) or {}
        notification_ids = data.get('notification_ids')
        
        marked_count = notification_service.mark_read(
            user_id=user_id,
            notification_ids=notification_ids
        )
        
        message = f'{marked_count} notification{"" if marked_count == 1 else "s"} marked as read'
        
        return success_response(
            data={'marked_count': marked_count},
            message=message,
        )
    except notification_service.NotificationError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@notifications_bp.route('/preferences', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def get_preferences():
    """
    Get notification and email preferences for the authenticated user.
    """
    try:
        user_id = get_jwt_identity()
        prefs = notification_service.get_user_preferences(user_id=user_id)
        return success_response(data=prefs)
    except notification_service.NotificationError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@notifications_bp.route('/preferences', methods=['PUT'])
@jwt_required()
@admin_or_staff_or_field_required
def update_preferences():
    """
    Update notification and email preferences for the authenticated user.
    """
    try:
        user_id = get_jwt_identity()
        data = request.get_json(silent=True) or {}
        prefs = notification_service.update_user_preferences(user_id=user_id, data=data)
        return success_response(
            data=prefs,
            message='Notification preferences updated successfully.',
        )
    except notification_service.NotificationError as exc:
        return error_response(exc.message, status_code=exc.status_code)

