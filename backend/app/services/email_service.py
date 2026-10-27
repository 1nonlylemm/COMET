import logging
import os
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from flask import current_app, render_template

from app.extensions import db
from app.models import CommunicationLog, EscalationNotice, LguProfile, MagicLink, NoticeRecipient, Project, ProjectRequirement
from app.services import access_service, audit_service, settings_service


logger = logging.getLogger(__name__)

SUPPORTED_DISPATCH_CHANNELS = ('email', 'dms', 'intranet', 'manual_print')
OUTSTANDING_REQUIREMENT_STATUSES = ('pending', 'under_review', 'non_compliant')
MAGIC_LINK_PURPOSE_LABEL = 'Read-Only External Checklist'


class DispatchError(Exception):
    def __init__(self, message, status_code=400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _public_magic_links_enabled():
    return bool(current_app.config.get('ENABLE_PUBLIC_MAGIC_LINKS', False))


def _ensure_public_magic_links_enabled(*, public=False):
    if _public_magic_links_enabled():
        return
    if public:
        raise DispatchError('Magic link not found.', 404)
    raise DispatchError('Public magic links are disabled for this deployment.', 403)


def _get_smtp_config():
    from app.services.integration_config_service import resolve_email_runtime_value
    host = resolve_email_runtime_value('SMTP_HOST')
    port = int(resolve_email_runtime_value('SMTP_PORT') or 587)
    username = resolve_email_runtime_value('SMTP_USERNAME')
    password = resolve_email_runtime_value('SMTP_PASSWORD')
    use_tls_raw = resolve_email_runtime_value('SMTP_USE_TLS')
    use_tls = use_tls_raw is True or str(use_tls_raw).lower() in ('true', '1', 'yes', 'on')
    mail_from = resolve_email_runtime_value('MAIL_FROM') or 'no-reply@example.local'
    return {
        'host': host,
        'port': port,
        'username': username,
        'password': password,
        'use_tls': use_tls,
        'mail_from': mail_from,
    }


def send_user_provisioning_email(email, first_name, temporary_password):
    login_url = os.environ.get('APP_LOGIN_URL', 'http://localhost:3000/login')
    branding = settings_service.get_branding()
    app_name = branding['app_name']
    app_tagline = branding['app_tagline']
    smtp_cfg = _get_smtp_config()
    from_address = smtp_cfg['mail_from']

    pst_now = datetime.now(timezone(timedelta(hours=8)))
    pst_timestamp = pst_now.strftime('%B %d, %Y %I:%M %p PST')

    subject = f'[{app_name}] Account: Your User Account Has Been Created'
    body = (
        f'Hello {first_name},\n\n'
        f'An administrator created your {app_name} account.\n\n'
        f'Temporary password: {temporary_password}\n'
        f'Login page: {login_url}\n\n'
        f'For security, change your password immediately after you sign in.\n\n'
        f'Security note: {app_name} will never ask you to provide your password through email.\n'
        f'This is an automated {app_name} notification. Generated in Philippine Standard Time ({pst_timestamp}).\n'
    )

    if current_app.config.get('TESTING'):
        logger.info('Testing mode is active. Skipping provisioning email for %s', email)
        return {
            'status': 'skipped',
            'message': 'Testing mode is active. Credentials were not emailed.',
            'recipient': email,
        }

    smtp_host = smtp_cfg['host']
    if not smtp_host:
        logger.info('SMTP is not configured. Skipping provisioning email for %s', email)
        return {
            'status': 'skipped',
            'message': 'SMTP is not configured. Credentials were not emailed.',
            'recipient': email,
        }

    smtp_port = smtp_cfg['port']
    smtp_username = smtp_cfg['username']
    smtp_password = smtp_cfg['password']
    use_tls = smtp_cfg['use_tls']

    html_body = None
    try:
        html_body = render_template(
            'email/user_provisioning.html',
            first_name=first_name,
            temporary_password=temporary_password,
            login_url=login_url,
            app_name=app_name,
            app_tagline=app_tagline,
            pst_timestamp=pst_timestamp,
        )
    except Exception as exc:
        logger.warning('Failed to render email/user_provisioning.html: %s', exc)

    message = EmailMessage()
    message['Subject'] = subject
    message['From'] = from_address
    message['To'] = email
    message.set_content(body)
    if html_body:
        message.add_alternative(html_body, subtype='html')

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
            if use_tls:
                server.starttls()
            if smtp_username and smtp_password:
                server.login(smtp_username, smtp_password)
            server.send_message(message)
    except Exception as exc:
        logger.exception('Failed to send provisioning email to %s', email)
        return {
            'status': 'failed',
            'message': str(exc),
            'recipient': email,
        }

    return {
        'status': 'sent',
        'message': 'Provisioning email sent successfully.',
        'recipient': email,
    }


def send_password_reset_email(email, reset_token, first_name=None):
    app_frontend_url = current_app.config.get('APP_FRONTEND_URL', 'http://localhost:3000').rstrip('/')
    reset_url = f"{app_frontend_url}/reset-password?token={reset_token}"
    branding = settings_service.get_branding()
    app_name = branding['app_name']
    app_tagline = branding['app_tagline']
    smtp_cfg = _get_smtp_config()
    from_address = smtp_cfg['mail_from']

    pst_now = datetime.now(timezone(timedelta(hours=8)))
    pst_timestamp = pst_now.strftime('%B %d, %Y %I:%M %p PST')

    subject = f'[{app_name}] Account: Password Reset Request'
    recipient_name = first_name or 'User'
    body = (
        f'Hello {recipient_name},\n\n'
        f'A password reset was requested for your {app_name} account.\n\n'
        f'To reset your password, visit the link below (valid for 15 minutes):\n'
        f'{reset_url}\n\n'
        f'If you did not request this password reset, please disregard this email or notify your system administrator immediately.\n\n'
        f'Security note: {app_name} will never ask you to provide your password through email.\n'
        f'This is an automated {app_name} notification. Generated in Philippine Standard Time ({pst_timestamp}).\n'
    )

    if current_app.config.get('TESTING'):
        logger.info('Testing mode is active. Skipping password reset email for %s', email)
        return {
            'status': 'skipped',
            'message': 'Testing mode is active. Reset token was not emailed.',
            'recipient': email,
            'token': reset_token,
        }

    smtp_host = smtp_cfg['host']
    if not smtp_host:
        logger.info('SMTP is not configured. Skipping password reset email for %s', email)
        return {
            'status': 'skipped',
            'message': 'SMTP is not configured.',
            'recipient': email,
        }

    smtp_port = smtp_cfg['port']
    smtp_username = smtp_cfg['username']
    smtp_password = smtp_cfg['password']
    use_tls = smtp_cfg['use_tls']

    html_body = None
    try:
        html_body = render_template(
            'email/password_reset.html',
            first_name=recipient_name,
            reset_url=reset_url,
            app_name=app_name,
            app_tagline=app_tagline,
            pst_timestamp=pst_timestamp,
        )
    except Exception as exc:
        logger.warning('Failed to render email/password_reset.html: %s', exc)

    message = EmailMessage()
    message['Subject'] = subject
    message['From'] = from_address
    message['To'] = email
    message.set_content(body)
    if html_body:
        message.add_alternative(html_body, subtype='html')

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
            if use_tls:
                server.starttls()
            if smtp_username and smtp_password:
                server.login(smtp_username, smtp_password)
            server.send_message(message)
    except Exception as exc:
        logger.exception('Failed to send password reset email to %s', email)
        return {'status': 'failed', 'message': str(exc), 'recipient': email}

    return {'status': 'sent', 'message': 'Password reset email sent.', 'recipient': email}


def send_security_alert_email(email, first_name, alert_type, details=None):
    branding = settings_service.get_branding()
    app_name = branding['app_name']
    app_tagline = branding['app_tagline']
    smtp_cfg = _get_smtp_config()
    from_address = smtp_cfg['mail_from']

    pst_now = datetime.now(timezone(timedelta(hours=8)))
    pst_timestamp = pst_now.strftime('%B %d, %Y %I:%M %p PST')

    alert_type_display = alert_type.replace("_", " ").title()
    subject = f'[{app_name}] Security Alert: {alert_type_display}'
    recipient_name = first_name or 'User'
    event_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    body = (
        f'Hello {recipient_name},\n\n'
        f'This is a security notification for your {app_name} account:\n'
        f'Event: {alert_type_display}\n'
        f'Time: {event_time}\n'
    )
    if details:
        for k, v in details.items():
            k_label = k.replace('_', ' ').title()
            body += f'{k_label}: {v}\n'
    body += (
        '\nIf you did not perform this action, please contact your administrator immediately.\n\n'
        f'Security note: {app_name} will never ask you to provide your password through email.\n'
        f'This is an automated {app_name} notification. Generated in Philippine Standard Time ({pst_timestamp}).\n'
    )

    if current_app.config.get('TESTING'):
        logger.info('Testing mode is active. Skipping security alert email for %s', email)
        return {'status': 'skipped', 'recipient': email}

    smtp_host = smtp_cfg['host']
    if not smtp_host:
        return {'status': 'skipped', 'recipient': email}

    smtp_port = smtp_cfg['port']
    smtp_username = smtp_cfg['username']
    smtp_password = smtp_cfg['password']
    use_tls = smtp_cfg['use_tls']

    html_body = None
    try:
        html_body = render_template(
            'email/security_alert.html',
            first_name=recipient_name,
            alert_type=alert_type,
            alert_type_display=alert_type_display,
            event_time=event_time,
            details=details or {},
            app_name=app_name,
            app_tagline=app_tagline,
            pst_timestamp=pst_timestamp,
        )
    except Exception as exc:
        logger.warning('Failed to render email/security_alert.html: %s', exc)

    message = EmailMessage()
    message['Subject'] = subject
    message['From'] = from_address
    message['To'] = email
    message.set_content(body)
    if html_body:
        message.add_alternative(html_body, subtype='html')

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
            if use_tls:
                server.starttls()
            if smtp_username and smtp_password:
                server.login(smtp_username, smtp_password)
            server.send_message(message)
    except Exception as exc:
        logger.exception('Failed to send security alert to %s', email)
        return {'status': 'failed', 'message': str(exc), 'recipient': email}

    return {'status': 'sent', 'message': 'Security alert sent.', 'recipient': email}

def _resolve_notification_presentation(*, notification, project_name, lgu_name, requirement_name, status_label, app_name):
    """
    Map operational notification semantics to the COMET Email Design System presentation variant,
    standardized subject line, contextual CTA label, and specialized visual cards.
    """
    ntype = getattr(notification, 'notification_type', '') or ''
    priority = (getattr(notification, 'priority', 'normal') or 'normal').lower()
    title = getattr(notification, 'title', '') or 'Notification'

    # Defaults
    variant = 'action'
    badge_theme = 'action'
    badge_label = 'ACTION REQUIRED'
    button_theme = 'primary'
    action_label = f'Open in {app_name}'
    subject = f'[{app_name}] Action Required: {title}'
    deadline_info = None
    waiting_info = None
    escalation_info = None
    notice_ref = None

    # 1. Critical Overdue Deadline / SLA Breached / Non-compliant Breach
    if ntype in ('sla_breached', 'compliance_breach') or 'overdue' in title.lower() or 'non-compliant' in title.lower():
        variant = 'critical'
        badge_theme = 'critical'
        button_theme = 'critical'
        if ntype == 'compliance_breach' or 'non-compliant' in title.lower():
            badge_label = 'NON-COMPLIANT'
            action_label = 'View Formal Findings'
            subject = f'[{app_name}] Critical: Document Marked Non-Compliant - {requirement_name or project_name or title}'
            deadline_info = {
                'headline': 'Document Marked Non-Compliant',
                'detail': f'Document "{requirement_name or "requirement"}" was marked non-compliant by review staff. Formal non-compliance findings have been recorded.',
                'is_overdue': True,
            }
        else:
            badge_label = 'DEADLINE OVERDUE'
            action_label = 'Open Escalation Center'
            subject = f'[{app_name}] Critical: Compliance Deadline Overdue - {project_name or title}'
            deadline_info = {
                'headline': 'Statutory Compliance Deadline Overdue',
                'detail': f'The statutory compliance deadline for {project_name or "this project"} has elapsed. Formal administrative escalation is required.',
                'is_overdue': True,
            }

    # 2. SLA Warning / Approaching Deadline
    elif ntype == 'sla_warning' or ('deadline' in title.lower() and ('working day' in title.lower() or 'approaching' in title.lower())):
        if '1 working day' in title.lower() or 't-1' in title.lower() or priority == 'critical':
            variant = 'critical'
            badge_theme = 'critical'
            badge_label = '1 WORKING DAY REMAINING'
            button_theme = 'critical'
            action_label = 'Open Deadline & Requirement'
            subject = f'[{app_name}] Urgent: 1 Working Day Remaining - {project_name or title}'
            deadline_info = {
                'headline': '1 Working Day Remaining',
                'detail': f'Statutory compliance milestone for {project_name or "project"} expires in 1 working day. Immediate submission is required.',
                'is_overdue': False,
            }
        else:
            variant = 'deadline'
            badge_theme = 'deadline'
            badge_label = '3 WORKING DAYS REMAINING'
            button_theme = 'deadline'
            action_label = 'Open Deadline & Requirement'
            subject = f'[{app_name}] Urgent: Compliance Deadline in 3 Working Days - {project_name or title}'
            deadline_info = {
                'headline': '3 Working Days Remaining',
                'detail': f'Statutory compliance milestone for {project_name or "project"} expires in 3 working days.',
                'is_overdue': False,
            }

    # 3. Escalations & Formal Notices
    elif ntype in ('escalation_generated', 'notice_pending_release', 'notice_pending_receipt', 'notice_follow_up_due') or 'notice' in title.lower():
        variant = 'escalation'
        badge_theme = 'escalation'
        button_theme = 'escalation'
        if ntype == 'notice_pending_release' or 'release' in title.lower():
            badge_label = 'NOTICE PENDING RELEASE'
            action_label = 'Release Notice'
            subject = f'[{app_name}] Action Required: Formal Notice Awaiting Release - {project_name or title}'
            escalation_info = {'detail': 'Finalized escalation notice has been approved and is awaiting release.'}
        elif ntype == 'notice_pending_receipt' or 'receipt' in title.lower():
            badge_label = 'RECORD RECEIPT'
            action_label = 'Record Notice Receipt'
            subject = f'[{app_name}] Action Required: Record Notice Receipt Date - {project_name or title}'
            escalation_info = {'detail': 'Dispatched escalation notice has not yet been acknowledged by the LGU.'}
        elif ntype == 'notice_follow_up_due' or 'follow-up' in title.lower():
            badge_label = 'FOLLOW-UP DUE'
            action_label = 'Conduct Notice Follow-Up'
            subject = f'[{app_name}] Action Required: Notice Follow-Up Due - {project_name or title}'
            escalation_info = {'detail': 'Notice 15 working-day response window has expired. Next escalation step is required.'}
        else:
            badge_label = 'FORMAL NOTICE GENERATED'
            action_label = 'Review Formal Notice'
            subject = f'[{app_name}] Escalation: Notice Generated - {project_name or title}'
            escalation_info = {'detail': f'Notice of Deficiencies has been officially generated for {project_name or "project"}.'}

    # 4. Compliance Reminders
    elif ntype in ('resubmission_unreviewed_reminder', 'submission_unreviewed_reminder', 'revision_pending_reminder', 'provincial_approval_reminder', 'requirement_missing_reminder'):
        variant = 'action'
        badge_theme = 'action'
        button_theme = 'primary'
        if ntype == 'resubmission_unreviewed_reminder':
            badge_label = 'REVIEW PENDING'
            action_label = 'Review Resubmission'
            subject = f'[{app_name}] Action Required: Resubmission Awaiting Review - {requirement_name or title}'
            waiting_info = {
                'current_state': 'Resubmitted by Field Officer',
                'time_waiting': 'Action Required',
                'action_expected': 'Staff Review & Verification'
            }
        elif ntype == 'submission_unreviewed_reminder':
            badge_label = 'REVIEW PENDING'
            action_label = 'Review Submission'
            subject = f'[{app_name}] Reminder: Submission Awaiting Review - {requirement_name or title}'
            waiting_info = {
                'current_state': 'Uploaded by Field Officer',
                'time_waiting': 'Action Required',
                'action_expected': 'Staff Verification'
            }
        elif ntype == 'revision_pending_reminder':
            if 'escalation' in title.lower():
                badge_label = 'REVISION ESCALATION'
                action_label = 'Open Requirement'
                subject = f'[{app_name}] Escalation: Unresolved Revision - {requirement_name or title}'
                waiting_info = {
                    'current_state': 'Returned for Revision (Unresolved)',
                    'time_waiting': 'Action Required',
                    'action_expected': 'Follow-Up with LGU'
                }
            else:
                badge_label = 'REVISION PENDING'
                action_label = 'Submit Revised Document'
                subject = f'[{app_name}] Reminder: Revision Pending Resubmission - {requirement_name or title}'
                waiting_info = {
                    'current_state': 'Returned for Revision',
                    'time_waiting': 'Action Required',
                    'action_expected': 'Address Deficiencies and Resubmit'
                }
        elif ntype == 'provincial_approval_reminder':
            badge_label = 'APPROVAL REQUIRED'
            action_label = 'Authorize Requirement'
            subject = f'[{app_name}] Action Required: Pending Provincial Approval - {requirement_name or title}'
            waiting_info = {
                'current_state': 'Staff Verified',
                'time_waiting': 'Action Required',
                'action_expected': 'Provincial Admin Approval'
            }
        else:
            badge_label = 'SUBMISSION PENDING'
            action_label = 'Upload Requirement'
            subject = f'[{app_name}] Reminder: Mandatory Requirement Pending - {requirement_name or title}'
            waiting_info = {
                'current_state': 'Document Not Uploaded',
                'time_waiting': 'Action Required',
                'action_expected': 'Field Officer Documentary Submission'
            }

    # 5. Privilege Overrides (Checked before generic success matching to prevent 'Approved' in title overshadowing)
    elif ntype in ('requirement_privilege_override', 'mar_privilege_override') or 'override' in title.lower():
        variant = 'action'
        badge_theme = 'action'
        badge_label = 'PRIVILEGE OVERRIDE'
        button_theme = 'primary'
        action_label = 'Review Audit Log'
        subject = f'[{app_name}] Audit Alert: Privilege Override Used - {requirement_name or project_name or title}'

    # 6. Success Events
    elif ntype in ('workflow_document_approved', 'workflow_staff_approved', 'mar_closed') or 'approved' in title.lower():
        variant = 'success'
        badge_theme = 'success'
        button_theme = 'success'
        if ntype == 'workflow_staff_approved' or 'staff' in title.lower():
            badge_label = 'STAFF VERIFIED'
            action_label = 'View Requirement'
            subject = f'[{app_name}] Workflow Update: Staff Review Cleared - {requirement_name or title}'
        elif ntype == 'mar_closed':
            badge_label = 'REPORT CLOSED'
            action_label = 'View Closed Report'
            subject = f'[{app_name}] Workflow Update: Management Action Report Closed - {project_name or title}'
        else:
            badge_label = 'APPROVED'
            action_label = 'View Approved Requirement'
            subject = f'[{app_name}] Workflow Update: Document Approved - {requirement_name or title}'

    # 6. Specific Action-Required Workflow Events
    elif ntype == 'workflow_document_returned' or 'returned' in title.lower() or 'revision' in title.lower():
        variant = 'action'
        badge_theme = 'action'
        badge_label = 'REVISION REQUIRED'
        button_theme = 'primary'
        action_label = 'Review Findings & Resubmit'
        subject = f'[{app_name}] Action Required: Document Returned for Revision - {requirement_name or project_name or title}'
        waiting_info = {
            'current_state': 'Returned for Revision',
            'time_waiting': 'Action Required',
            'action_expected': 'Review Deficiencies and Resubmit'
        }

    elif ntype == 'workflow_pending_provincial_approval':
        variant = 'action'
        badge_theme = 'action'
        badge_label = 'APPROVAL REQUIRED'
        button_theme = 'primary'
        action_label = 'Authorize Requirement'
        subject = f'[{app_name}] Action Required: Authorize Document - {requirement_name or title}'
        waiting_info = {
            'current_state': 'Pending Provincial Admin Approval',
            'time_waiting': 'Action Required',
            'action_expected': 'Final Provincial Authorization'
        }

    elif ntype == 'workflow_document_submitted':
        variant = 'action'
        badge_theme = 'action'
        badge_label = 'VERIFICATION REQUIRED'
        button_theme = 'primary'
        if 'resubmitted' in title.lower() or 'revised' in title.lower():
            action_label = 'Review Resubmission'
            subject = f'[{app_name}] Action Required: Revised Document Resubmitted - {requirement_name or title}'
        else:
            action_label = 'Review Submission'
            subject = f'[{app_name}] Action Required: Document Submitted for Review - {requirement_name or title}'

    elif ntype == 'project_reopened' or 'reopened' in title.lower():
        variant = 'action'
        badge_theme = 'action'
        badge_label = 'PROJECT REOPENED'
        button_theme = 'primary'
        action_label = 'Open Project Dashboard'
        subject = f'[{app_name}] Workflow Update: Project Reopened - {project_name or title}'


    elif ntype == 'mar_generated':
        variant = 'action'
        badge_theme = 'action'
        badge_label = 'ACTION REQUIRED'
        button_theme = 'primary'
        action_label = 'Review Action Report'
        subject = f'[{app_name}] Action Required: Management Action Report Generated - {project_name or title}'

    elif ntype == 'mar_submitted':
        variant = 'action'
        badge_theme = 'action'
        badge_label = 'DECISION REQUIRED'
        button_theme = 'primary'
        action_label = 'Review & Act on Report'
        subject = f'[{app_name}] Action Required: Management Action Report Awaiting Decision - {project_name or title}'

    # 7. Informational Workflow Events
    elif ntype in ('submission_received', 'mar_acted'):
        variant = 'informational'
        badge_theme = 'informational'
        button_theme = 'primary'
        if ntype == 'submission_received':
            badge_label = 'SUBMISSION RECEIVED'
            action_label = 'View Submission'
            subject = f'[{app_name}] Workflow Update: Submission Received - {project_name or title}'
        else:
            badge_label = 'DIRECTIVES ISSUED'
            action_label = 'View Action Report'
            subject = f'[{app_name}] Workflow Update: Management Action Directives Recorded - {project_name or title}'

    # 8. Fallback priority handling
    else:
        if priority == 'critical':
            variant = 'critical'
            badge_theme = 'critical'
            badge_label = 'CRITICAL ALERT'
            button_theme = 'critical'
            subject = f'[{app_name}] Critical Alert: {title}'
        elif priority == 'high':
            variant = 'action'
            badge_theme = 'action'
            badge_label = 'HIGH PRIORITY'
            button_theme = 'primary'
            subject = f'[{app_name}] Action Required: {title}'
        elif priority == 'low':
            variant = 'informational'
            badge_theme = 'informational'
            badge_label = 'INFORMATIONAL'
            button_theme = 'primary'
            subject = f'[{app_name}] Update: {title}'
        else:
            variant = 'action'
            badge_theme = 'action'
            badge_label = 'NOTIFICATION'
            button_theme = 'primary'
            subject = f'[{app_name}] Notification: {title}'

    return {
        'variant': variant,
        'badge_theme': badge_theme,
        'badge_label': badge_label,
        'button_theme': button_theme,
        'action_label': action_label,
        'subject': subject,
        'deadline_info': deadline_info,
        'waiting_info': waiting_info,
        'escalation_info': escalation_info,
        'notice_ref': notice_ref,
    }


def _format_requirement_status_label(status):
    """
    Format internal ProjectRequirement status / workflow_status machine values into
    human-readable labels consistent with COMET UI formatters.
    """
    if not status:
        return None
    labels = {
        'draft': 'Draft',
        'pending': 'Pending',
        'under_review': 'Under Review',
        'returned_for_revision': 'Returned for Revision',
        'non_compliant': 'Non-Compliant',
        'compliant': 'Compliant',
        'waived': 'Waived',
        'submitted': 'Submitted',
        'under_verification': 'Under Verification',
        'staff_approved': 'Staff Approved',
        'pending_provincial_approval': 'Pending Provincial Approval',
        'approved': 'Approved',
        'resubmitted': 'Resubmitted',
        'not_applicable': 'Not Applicable',
    }
    raw = str(status).strip()
    return labels.get(raw, raw.replace('_', ' ').title())


def send_notification_email(notification, recipient):
    """
    Send a standardized COMET email notification to an authenticated user.
    
    Enforces:
    - Configured SMTP credentials
    - Standardized application branding and visual purpose presentation
    - Project / LGU / Requirement context
    - Safe action URL (pointing to frontend application route, never tokens/passwords)
    - Isolation from business transactions
    """
    branding = settings_service.get_branding()
    app_name = branding['app_name']
    app_tagline = branding['app_tagline']
    smtp_cfg = _get_smtp_config()
    from_address = smtp_cfg['mail_from']
    app_frontend_url = current_app.config.get('APP_FRONTEND_URL', 'http://localhost:3000').rstrip('/')

    priority = getattr(notification, 'priority', 'normal') or 'normal'

    # Resolve context
    project_name = None
    lgu_name = None
    requirement_name = None
    status_label = None

    if getattr(notification, 'project_id', None):
        project = db.session.get(Project, notification.project_id)
        if project:
            project_name = project.project_name
            lgu = db.session.get(LguProfile, project.lgu_id) if project.lgu_id else None
            if lgu:
                lgu_name = lgu.name

    if getattr(notification, 'related_entity_type', None) == 'project_requirement' and getattr(notification, 'related_entity_id', None):
        requirement = db.session.get(ProjectRequirement, notification.related_entity_id)
        if requirement:
            requirement_name = requirement.requirement_name
            status_label = _format_requirement_status_label(requirement.workflow_status or requirement.status)
            if not project_name and requirement.project:
                project_name = requirement.project.project_name
    elif getattr(notification, 'related_entity_type', None) == 'escalation_notice' and getattr(notification, 'related_entity_id', None):
        notice = db.session.get(EscalationNotice, notification.related_entity_id)
        if notice:
            status_label = notice.status.replace('_', ' ').title()
            if not project_name and notice.project:
                project_name = notice.project.project_name

    # Safe action URL
    safe_action_url = None
    if getattr(notification, 'action_url', None):
        action_path = notification.action_url if notification.action_url.startswith('/') else f'/{notification.action_url}'
        safe_action_url = f'{app_frontend_url}{action_path}'
    elif getattr(notification, 'project_id', None):
        safe_action_url = f'{app_frontend_url}/dashboard/projects/{notification.project_id}'

    # PST timestamp (UTC+8)
    pst_now = datetime.now(timezone(timedelta(hours=8)))
    pst_timestamp = pst_now.strftime('%B %d, %Y %I:%M %p PST')

    # Resolve Design System Presentation Variant & Subject
    presentation = _resolve_notification_presentation(
        notification=notification,
        project_name=project_name,
        lgu_name=lgu_name,
        requirement_name=requirement_name,
        status_label=status_label,
        app_name=app_name,
    )

    subject = presentation['subject']
    variant = presentation['variant']
    badge_theme = presentation['badge_theme']
    badge_label = presentation['badge_label']
    button_theme = presentation['button_theme']
    action_label = presentation['action_label']
    deadline_info = presentation['deadline_info']
    waiting_info = presentation['waiting_info']
    escalation_info = presentation['escalation_info']
    notice_ref = presentation['notice_ref']

    # Plain text fallback body
    plain_text_lines = [
        f'{app_name}',
    ]
    if app_tagline:
        plain_text_lines.append(f'{app_tagline}')
    plain_text_lines.extend([
        '',
        f'[{badge_label}]',
        notification.title,
        '=' * len(notification.title),
        '',
    ])
    if deadline_info:
        plain_text_lines.extend([
            f'Deadline Status: {deadline_info["headline"]}',
            f'{deadline_info["detail"]}',
            '',
        ])
    if waiting_info:
        plain_text_lines.extend([
            f'Current State: {waiting_info["current_state"]}',
            f'Time Waiting: {waiting_info["time_waiting"]}',
            f'Action Expected: {waiting_info["action_expected"]}',
            '',
        ])
    if escalation_info:
        plain_text_lines.extend([
            f'Formal Notice: {escalation_info["detail"]}',
            '',
        ])
    if project_name:
        plain_text_lines.append(f'Project: {project_name}')
    if lgu_name:
        plain_text_lines.append(f'LGU: {lgu_name}')
    if requirement_name:
        plain_text_lines.append(f'Requirement: {requirement_name}')
    if status_label:
        plain_text_lines.append(f'Status: {status_label}')
    plain_text_lines.extend([
        '',
        "Why you're receiving this:",
        notification.message or '',
        '',
    ])
    if safe_action_url:
        plain_text_lines.extend([
            f'Action: {action_label} ({safe_action_url})',
            '',
        ])
    plain_text_lines.extend([
        f'Security note: {app_name} will never ask you to provide your password through email.',
        '',
        f'This is an automated {app_name} notification. Generated in Philippine Standard Time ({pst_timestamp}).',
    ])
    plain_text_body = '\n'.join(plain_text_lines)

    # Render HTML template
    try:
        html_body = render_template(
            'email/notification.html',
            notification=notification,
            recipient=recipient,
            priority_level=priority,
            variant=variant,
            badge_theme=badge_theme,
            badge_label=badge_label,
            button_theme=button_theme,
            action_label=action_label,
            deadline_info=deadline_info,
            waiting_info=waiting_info,
            escalation_info=escalation_info,
            notice_ref=notice_ref,
            project_name=project_name,
            lgu_name=lgu_name,
            requirement_name=requirement_name,
            status_label=status_label,
            safe_action_url=safe_action_url,
            pst_timestamp=pst_timestamp,
            app_name=app_name,
            app_tagline=app_tagline,
        )
    except Exception as exc:
        logger.warning('Failed to render email/notification.html, using fallback text: %s', exc)
        html_body = None


    recipient_email = recipient.email if hasattr(recipient, 'email') else str(recipient)

    if current_app.config.get('TESTING'):
        logger.info('Testing mode is active. Skipping email dispatch to %s', recipient_email)
        return {
            'status': 'sent',
            'message': 'Testing mode skipped network delivery.',
            'recipient': recipient_email,
            'subject': subject,
        }

    smtp_host = smtp_cfg['host']
    if not smtp_host:
        logger.info('SMTP is not configured. Skipping email dispatch for %s', recipient_email)
        return {
            'status': 'skipped',
            'message': 'SMTP is not configured.',
            'recipient': recipient_email,
        }

    smtp_port = smtp_cfg['port']
    smtp_username = smtp_cfg['username']
    smtp_password = smtp_cfg['password']
    use_tls = smtp_cfg['use_tls']

    message = EmailMessage()
    message['Subject'] = subject
    message['From'] = from_address
    message['To'] = recipient_email
    message.set_content(plain_text_body)
    if html_body:
        message.add_alternative(html_body, subtype='html')

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
            if use_tls:
                server.starttls()
            if smtp_username and smtp_password:
                server.login(smtp_username, smtp_password)
            server.send_message(message)
    except Exception as exc:
        logger.exception('Failed to send notification email to %s', recipient_email)
        return {
            'status': 'failed',
            'message': str(exc),
            'recipient': recipient_email,
        }

    return {
        'status': 'sent',
        'message': 'Notification email sent successfully.',
        'recipient': recipient_email,
    }


def revoke_magic_links(*, lgu_id=None, project_id=None, user_id=None, reason=None):
    query = MagicLink.query.filter_by(is_used=False)
    if lgu_id:
        query = query.filter_by(lgu_id=lgu_id)
    if project_id:
        query = query.filter_by(project_id=project_id)

    links = query.all()
    count = 0
    now = datetime.now(timezone.utc)
    for link in links:
        link.is_used = True
        link.used_at = now
        count += 1
    db.session.commit()

    if count > 0:
        audit_service.log_action(
            user_id=_coerce_optional_user_id(user_id),
            action='revoke',
            entity_type='magic_link',
            entity_id=project_id or lgu_id or 0,
            old_value=None,
            new_value={'lgu_id': lgu_id, 'project_id': project_id, 'revoked_count': count, 'reason': reason},
        )
    return count


def create_magic_link(
    *,
    notice_id=None,
    project_id=None,
    expires_in_days=None,
    intended_recipient_name=None,
    intended_recipient_role=None,
    user_id=None,
):
    _ensure_public_magic_links_enabled()
    notice = _get_notice_with_access(notice_id, user_id=user_id) if notice_id is not None else None
    if notice is None and project_id is None:
        raise DispatchError('Either notice_id or project_id is required.', 422)

    project = notice.project if notice is not None else _get_project_with_access(project_id, user_id=user_id)
    lgu = db.session.get(LguProfile, project.lgu_id)
    if not lgu:
        raise DispatchError('LGU not found for this project.', 404)

    expiry_days = _coerce_expiry_days(expires_in_days)
    link = MagicLink(
        lgu_id=lgu.id,
        project_id=project.id,
        notice_id=notice.id if notice is not None else None,
        created_by=_coerce_optional_user_id(user_id),
        token=MagicLink.generate_token(),
        intended_recipient_name=_clean_text(intended_recipient_name),
        intended_recipient_role=_clean_text(intended_recipient_role),
        expires_at=datetime.now(timezone.utc) + timedelta(days=expiry_days),
    )
    db.session.add(link)
    db.session.commit()

    audit_service.log_action(
        user_id=_coerce_optional_user_id(user_id),
        action='create',
        entity_type='magic_link',
        entity_id=link.id,
        old_value=None,
        new_value=_serialize_magic_link(link),
    )
    return _serialize_magic_link(link)


def get_magic_link_view(token):
    _ensure_public_magic_links_enabled(public=True)
    link = MagicLink.query.filter_by(token=(token or '').strip()).first()
    if not link:
        raise DispatchError('Magic link not found.', 404)
    if link.is_expired:
        raise DispatchError('This magic link has expired.', 410)
    if link.is_used:
        raise DispatchError('This magic link has already been used.', 410)

    project = _resolve_project_for_magic_link(link)
    lgu = db.session.get(LguProfile, link.lgu_id) if link.lgu_id else None
    notice = _resolve_notice_for_magic_link(link, project)
    requirements = (
        ProjectRequirement.query
        .filter_by(project_id=project.id, is_active=True)
        .order_by(ProjectRequirement.phase_name.asc(), ProjectRequirement.sort_order.asc(), ProjectRequirement.id.asc())
        .all()
    )
    applicable_requirements = [item for item in requirements if getattr(item, 'applicability', 'applicable') == 'applicable']
    not_applicable_requirements = [item for item in requirements if getattr(item, 'applicability', 'applicable') == 'not_applicable']
    outstanding_requirements = [item for item in applicable_requirements if item.status in OUTSTANDING_REQUIREMENT_STATUSES]
    compliance_summary = {
        'total_requirements': len(requirements),
        'applicable_requirements': len(applicable_requirements),
        'not_applicable_requirements': len(not_applicable_requirements),
        'outstanding_requirements': len(outstanding_requirements),
        'compliant_requirements': sum(1 for item in applicable_requirements if item.status in ('compliant', 'waived')),
    }

    now = datetime.now(timezone.utc)
    link.access_count = int(link.access_count or 0) + 1
    link.last_accessed_at = now
    if not link.is_used:
        link.is_used = True
        link.used_at = now
    db.session.commit()

    return {
        'token': link.token,
        'purpose_label': MAGIC_LINK_PURPOSE_LABEL,
        'project_id': project.id,
        'project_name': project.project_name,
        'fiscal_year': project.fiscal_year,
        'current_phase': project.current_phase,
        'overall_status': project.overall_status,
        'program_name': project.program.name if project.program else None,
        'lgu_id': lgu.id if lgu else None,
        'lgu_name': lgu.name if lgu else None,
        'municipality': lgu.municipality if lgu else None,
        'province': lgu.province if lgu else None,
        'intended_recipient_name': link.intended_recipient_name,
        'intended_recipient_role': link.intended_recipient_role,
        'expires_at': _isoformat(link.expires_at),
        'generated_at': _isoformat(link.created_at),
        'latest_notice': _serialize_public_notice(notice),
        'compliance_summary': compliance_summary,
        'outstanding_requirements': [_serialize_public_requirement(item) for item in outstanding_requirements],
        'not_applicable_requirements': [_serialize_public_requirement(item) for item in not_applicable_requirements],
    }


def prepare_notice_dispatch(
    notice_id,
    *,
    channel,
    magic_link_id=None,
    recipient_name=None,
    recipient_destination=None,
    recipient_office=None,
    reference_no=None,
    remarks=None,
    user_id=None,
):
    notice = _get_notice_with_access(notice_id, user_id=user_id)
    project = notice.project
    lgu = db.session.get(LguProfile, project.lgu_id) if project else None
    if not project or not lgu:
        raise DispatchError('Project or LGU context for this notice is incomplete.', 404)

    normalized_channel = _normalize_channel(channel)
    if magic_link_id:
        _ensure_public_magic_links_enabled()
    magic_link = _get_magic_link_for_notice(magic_link_id, notice, user_id=user_id) if magic_link_id else None
    resolved_recipient_name = _clean_text(recipient_name) or magic_link.intended_recipient_name if magic_link else _clean_text(recipient_name)
    resolved_recipient_name = resolved_recipient_name or _default_dispatch_recipient_name(lgu)
    resolved_destination = _clean_text(recipient_destination) or _default_dispatch_destination(normalized_channel, lgu)
    resolved_office = _clean_text(recipient_office) or _default_dispatch_office(lgu)
    magic_link_url = _public_magic_link_url(magic_link.token) if magic_link else None
    subject = _build_dispatch_subject(notice, project, lgu)
    body = _build_dispatch_body(
        notice=notice,
        project=project,
        lgu=lgu,
        channel=normalized_channel,
        recipient_name=resolved_recipient_name,
        recipient_destination=resolved_destination,
        recipient_office=resolved_office,
        reference_no=_clean_text(reference_no),
        remarks=_clean_text(remarks),
        magic_link_url=magic_link_url,
    )

    return {
        'notice_id': notice.id,
        'channel': normalized_channel,
        'reference_no': _clean_text(reference_no),
        'recipient_name': resolved_recipient_name,
        'recipient_destination': resolved_destination,
        'recipient_office': resolved_office,
        'magic_link_id': magic_link.id if magic_link else None,
        'magic_link_url': magic_link_url,
        'subject': subject,
        'body': body,
        'attachments': _build_attachment_manifest(notice),
    }


def record_notice_dispatch(
    notice_id,
    *,
    channel,
    magic_link_id=None,
    recipient_name=None,
    recipient_destination=None,
    recipient_office=None,
    reference_no=None,
    remarks=None,
    user_id=None,
):
    preview = prepare_notice_dispatch(
        notice_id,
        channel=channel,
        magic_link_id=magic_link_id,
        recipient_name=recipient_name,
        recipient_destination=recipient_destination,
        recipient_office=recipient_office,
        reference_no=reference_no,
        remarks=remarks,
        user_id=user_id,
    )
    notice = _get_notice_with_access(notice_id, user_id=user_id)
    now = datetime.now(timezone.utc)
    communication = CommunicationLog(
        lgu_id=notice.project.lgu_id,
        sent_by=_coerce_optional_user_id(user_id),
        communication_type='escalation_notice',
        channel=preview['channel'],
        subject=preview['subject'],
        body=preview['body'],
        recipient_email=_default_dispatch_email(preview['channel'], notice.project.lgu),
        recipient_name=preview['recipient_name'],
        recipient_destination=preview['recipient_destination'],
        recipient_office=preview['recipient_office'],
        reference_no=preview['reference_no'],
        related_notice_id=notice.id,
        magic_link_id=preview['magic_link_id'],
        delivery_status='sent',
        sent_at=now,
        posted_at=now,
        remarks=_clean_text(remarks),
    )
    db.session.add(communication)

    before_notice = _serialize_notice_status(notice)
    if notice.status != 'acknowledged':
        notice.status = 'sent'
    if notice.sent_at is None:
        notice.sent_at = now

    for recipient in notice.recipients.order_by(NoticeRecipient.id.asc()).all():
        recipient.delivery_method = preview['channel']
        recipient.delivery_status = 'sent'
        if recipient.sent_at is None:
            recipient.sent_at = now

    db.session.commit()

    audit_service.log_action(
        user_id=_coerce_optional_user_id(user_id),
        action='dispatch',
        entity_type='escalation_notice',
        entity_id=notice.id,
        old_value=before_notice,
        new_value=_serialize_notice_status(notice),
    )
    audit_service.log_action(
        user_id=_coerce_optional_user_id(user_id),
        action='create',
        entity_type='communication_log',
        entity_id=communication.id,
        old_value=None,
        new_value=_serialize_communication(communication),
    )

    return {
        'communication': _serialize_communication(communication),
        'notice': _serialize_notice_status(notice),
    }


def list_notice_dispatch_history(notice_id, user_id=None):
    notice = _get_notice_with_access(notice_id, user_id=user_id)
    communications = (
        CommunicationLog.query
        .filter_by(related_notice_id=notice.id)
        .order_by(CommunicationLog.created_at.desc(), CommunicationLog.id.desc())
        .all()
    )
    return [_serialize_communication(item) for item in communications]


def list_notice_magic_links(notice_id, user_id=None):
    notice = _get_notice_with_access(notice_id, user_id=user_id)
    links = (
        MagicLink.query
        .filter_by(notice_id=notice.id)
        .order_by(MagicLink.created_at.desc(), MagicLink.id.desc())
        .all()
    )
    return [_serialize_magic_link(item) for item in links]


def _serialize_magic_link(link):
    return {
        'id': link.id,
        'token': link.token,
        'url': _public_magic_link_url(link.token) if _public_magic_links_enabled() else None,
        'lgu_id': link.lgu_id,
        'project_id': link.project_id,
        'notice_id': getattr(link, 'notice_id', None),
        'intended_recipient_name': link.intended_recipient_name,
        'intended_recipient_role': link.intended_recipient_role,
        'expires_at': _isoformat(link.expires_at),
        'is_used': bool(link.is_used),
        'used_at': _isoformat(link.used_at),
        'access_count': int(link.access_count or 0),
        'last_accessed_at': _isoformat(link.last_accessed_at),
        'created_at': _isoformat(link.created_at),
        'is_expired': link.is_expired,
    }


def _serialize_public_requirement(requirement):
    is_na = getattr(requirement, 'applicability', 'applicable') == 'not_applicable'
    status_label = 'Not Applicable' if is_na else _public_status_label(requirement.status)
    return {
        'id': requirement.id,
        'requirement_name': requirement.requirement_name,
        'annex_reference': requirement.annex_reference,
        'phase_name': requirement.phase_name,
        'status': requirement.status,
        'applicability': getattr(requirement, 'applicability', 'applicable'),
        'applicability_reason': getattr(requirement, 'applicability_reason', None),
        'public_status_label': status_label,
        'is_mandatory': bool(requirement.is_mandatory),
        'has_sla': bool(requirement.has_sla),
        'sla_days': requirement.sla_days,
    }


def _serialize_public_notice(notice):
    if not notice:
        return None
    return {
        'id': notice.id,
        'notice_type': notice.notice_type,
        'title': notice.title,
        'status': notice.status,
        'generated_at': _isoformat(notice.generated_at),
    }


def _serialize_communication(communication):
    return {
        'id': communication.id,
        'lgu_id': communication.lgu_id,
        'sent_by': communication.sent_by,
        'communication_type': communication.communication_type,
        'channel': communication.channel,
        'subject': communication.subject,
        'body': communication.body,
        'recipient_email': communication.recipient_email,
        'recipient_name': communication.recipient_name,
        'recipient_destination': communication.recipient_destination,
        'recipient_office': communication.recipient_office,
        'reference_no': communication.reference_no,
        'related_notice_id': communication.related_notice_id,
        'magic_link_id': communication.magic_link_id,
        'delivery_status': communication.delivery_status,
        'sent_at': _isoformat(communication.sent_at),
        'posted_at': _isoformat(communication.posted_at),
        'remarks': communication.remarks,
        'created_at': _isoformat(communication.created_at),
    }


def _serialize_notice_status(notice):
    return {
        'id': notice.id,
        'status': notice.status,
        'sent_at': _isoformat(notice.sent_at),
        'acknowledged_at': _isoformat(notice.acknowledged_at),
        'updated_at': _isoformat(notice.updated_at),
    }


def _build_dispatch_subject(notice, project, lgu):
    notice_label = notice.title or notice.notice_type.replace('_', ' ').title()
    return f'{notice_label} | {project.project_name} | {lgu.name}'


def _build_dispatch_body(
    *,
    notice,
    project,
    lgu,
    channel,
    recipient_name,
    recipient_destination,
    recipient_office,
    reference_no,
    remarks,
    magic_link_url,
):
    channel_label = {
        'dms': 'DMS posting',
        'intranet': 'intranet posting',
        'manual_print': 'printed dispatch',
        'email': 'email dispatch',
    }[channel]
    lines = [
        f'Recipient: {recipient_name}',
        f'Destination: {recipient_destination}',
        f'Office: {recipient_office}',
        f'Channel: {channel_label}',
    ]
    if reference_no:
        lines.append(f'Reference No.: {reference_no}')
    lines.extend([
        '',
        f'Please post and release the attached {notice.title} for {lgu.name} regarding {project.project_name}.',
        f'The packet was prepared through {settings_service.get_app_name()} and should be attached to the official transmittal.',
    ])
    if magic_link_url:
        lines.extend([
            '',
            'Read-only compliance checklist link for the field officer / LGU:',
            magic_link_url,
        ])
    lines.extend([
        '',
        'Required attachments:',
        *[f'- {item}' for item in _build_attachment_manifest(notice)],
    ])
    if remarks:
        lines.extend(['', f'Remarks: {remarks}'])
    return '\n'.join(lines)


def _build_attachment_manifest(notice):
    label = notice.title or notice.notice_type.replace('_', ' ').title()
    return [
        f'{label} PDF',
        f'{label} DOCX',
        'Updated Annex C checklist summary',
    ]


def _public_magic_link_url(token):
    base_url = current_app.config.get('APP_FRONTEND_URL', 'http://localhost:3000').rstrip('/')
    return f'{base_url}/magic-links/{token}'


def _resolve_project_for_magic_link(link):
    project = db.session.get(Project, link.project_id) if link.project_id else None
    if project:
        return project
    if getattr(link, 'notice_id', None):
        notice = db.session.get(EscalationNotice, link.notice_id)
        if notice and notice.project:
            return notice.project
    raise DispatchError('Project not found for this magic link.', 404)


def _resolve_notice_for_magic_link(link, project):
    if getattr(link, 'notice_id', None):
        notice = db.session.get(EscalationNotice, link.notice_id)
        if notice:
            return notice
    return (
        EscalationNotice.query
        .filter_by(project_id=project.id)
        .order_by(EscalationNotice.generated_at.desc(), EscalationNotice.id.desc())
        .first()
    )


def _get_project_with_access(project_id, user_id=None):
    try:
        if user_id is not None:
            return access_service.ensure_project_access(project_id, user_id)
    except access_service.AccessError as exc:
        raise DispatchError(exc.message, exc.status_code)

    project = db.session.get(Project, project_id)
    if not project:
        raise DispatchError('Project not found.', 404)
    return project


def _get_notice_with_access(notice_id, user_id=None):
    notice = db.session.get(EscalationNotice, notice_id)
    if not notice:
        raise DispatchError('Escalation notice not found.', 404)
    _get_project_with_access(notice.project_id, user_id=user_id)
    return notice


def _get_magic_link_for_notice(magic_link_id, notice, user_id=None):
    link = db.session.get(MagicLink, magic_link_id)
    if not link:
        raise DispatchError('Magic link not found.', 404)
    if getattr(link, 'notice_id', None) != notice.id:
        raise DispatchError('Magic link does not belong to this notice.', 422)
    _get_project_with_access(link.project_id or notice.project_id, user_id=user_id)
    return link


def _coerce_expiry_days(value):
    if value in (None, ''):
        return max(1, int(current_app.config.get('MAGIC_LINK_EXPIRY_DAYS', 15)))
    try:
        value = int(value)
    except (TypeError, ValueError):
        raise DispatchError('expires_in_days must be an integer.', 422)
    if value < 1 or value > 60:
        raise DispatchError('expires_in_days must be between 1 and 60.', 422)
    return value


def _normalize_channel(channel):
    normalized = (channel or '').strip().lower()
    if normalized not in SUPPORTED_DISPATCH_CHANNELS:
        raise DispatchError(f'channel must be one of: {", ".join(SUPPORTED_DISPATCH_CHANNELS)}', 422)
    return normalized


def _coerce_optional_user_id(user_id):
    if user_id in (None, ''):
        return None
    try:
        return int(user_id)
    except (TypeError, ValueError):
        raise DispatchError('Invalid user identity.', 422)


def _default_dispatch_recipient_name(lgu):
    return lgu.contact_person or lgu.mayor_name or lgu.name


def _default_dispatch_destination(channel, lgu):
    defaults = {
        'dms': f'{lgu.name} DMS Inbox',
        'intranet': f'{lgu.name} Intranet Board',
        'manual_print': f'{lgu.name} printed packet',
        'email': lgu.contact_email or lgu.mayor_email or '',
    }
    return defaults[channel]


def _default_dispatch_office(lgu):
    return lgu.name


def _default_dispatch_email(channel, lgu):
    if channel != 'email':
        return None
    return lgu.contact_email or lgu.mayor_email


def _public_status_label(status):
    labels = {
        'pending': 'Still Needed',
        'under_review': 'Under Review',
        'non_compliant': 'For Rectification',
        'compliant': 'Submitted and Accepted',
        'waived': 'Waived',
        'not_applicable': 'Not Applicable',
    }
    return labels.get(status, status.replace('_', ' ').title())


def _isoformat(value):
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _clean_text(value):
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None
