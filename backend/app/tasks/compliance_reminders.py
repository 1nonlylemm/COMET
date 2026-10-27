from app.tasks import celery_app
from app.services import compliance_reminder_service


@celery_app.task(name='app.tasks.compliance_reminders.evaluate_compliance_reminders')
def evaluate_compliance_reminders():
    """Evaluate compliance reminders across active projects and requirements."""
    return compliance_reminder_service.evaluate_compliance_reminders()
