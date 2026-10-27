from app.services import sla_service
from app.tasks import celery_app


@celery_app.task(name='app.tasks.sla_monitor.monitor_overdue_deadlines')
def monitor_overdue_deadlines():
    """Flag overdue unresolved SLA deadlines for downstream escalation."""
    return sla_service.monitor_overdue_deadlines()
