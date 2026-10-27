import os

from celery import Celery
from celery import Task

from app import create_app


def _resolve_config_name():
    explicit = os.environ.get('FLASK_CONFIG') or os.environ.get('APP_CONFIG')
    if explicit:
        return explicit

    flask_env = os.environ.get('FLASK_ENV')
    if flask_env in {'development', 'production', 'testing'}:
        return flask_env

    return 'development'


def create_celery_app(config_name=None):
    flask_app = create_app(config_name or _resolve_config_name())

    class FlaskTask(Task):
        def __call__(self, *args, **kwargs):
            from app.logging_config import clear_celery_context, set_celery_context
            from app.services.operational_event_service import record_operational_event
            from celery.exceptions import Ignore, Retry

            req = getattr(self, 'request', None)
            task_id = getattr(req, 'id', None) or getattr(self, 'request_id', None)
            attempt = (getattr(req, 'retries', 0) or 0) + 1 if req else 1
            set_celery_context(task_id=task_id, task_name=self.name, attempt=attempt)

            from flask import current_app, has_app_context
            active_app = current_app._get_current_object() if has_app_context() else flask_app

            try:
                with active_app.app_context():
                    try:
                        return self.run(*args, **kwargs)
                    except (Retry, Ignore):
                        raise
                    except Exception as task_exc:
                        record_operational_event(
                            severity='ERROR',
                            component='celery_worker',
                            event_name='task_failure',
                            message=f"Celery task '{self.name}' failed: {task_exc}",
                            operation_id=str(task_id) if task_id else None,
                            context_data={
                                'task_name': self.name,
                                'task_id': str(task_id) if task_id else None,
                                'attempt': attempt,
                            },
                            exc_info=task_exc,
                        )
                        raise
            finally:
                clear_celery_context()

    celery = Celery(
        flask_app.import_name,
        task_cls=FlaskTask,
        include=[
            'app.tasks.sla_monitor',
            'app.tasks.escalation_engine',
            'app.tasks.notice_follow_up',
            'app.tasks.db_backup',
            'app.tasks.notification_dispatcher',
            'app.tasks.compliance_reminders',
            'app.tasks.operational_event_cleanup',
            'app.tasks.matcher_preview',
        ],
    )
    celery.conf.update(
        broker_url=flask_app.config['CELERY_BROKER_URL'],
        result_backend=flask_app.config['CELERY_RESULT_BACKEND'],
        beat_schedule=flask_app.config.get('CELERY_BEAT_SCHEDULE', {}),
        timezone='UTC',
    )
    celery.set_default()
    celery.conf.beat_schedule.setdefault('matcher-preview-cleanup', {
        'task': 'app.tasks.matcher_preview.cleanup', 'schedule': 1800,
    })
    celery.conf.beat_schedule.setdefault('matcher-preview-recover', {
        'task': 'app.tasks.matcher_preview.recover', 'schedule': 60,
    })
    flask_app.extensions['celery'] = celery
    return celery


celery_app = create_celery_app()
