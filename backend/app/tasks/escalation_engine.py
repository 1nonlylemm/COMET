from app.services import escalation_service
from app.tasks import celery_app


@celery_app.task(name='app.tasks.escalation_engine.process_auto_escalations')
def process_auto_escalations():
    """Generate the next escalation notices for overdue unresolved SLA deadlines."""
    return escalation_service.process_auto_escalations()
