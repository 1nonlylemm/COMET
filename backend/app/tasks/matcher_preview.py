from app.tasks import celery_app


@celery_app.task(name='app.tasks.matcher_preview.run', acks_late=True, reject_on_worker_lost=True)
def run(job_id):
    from app.services.matcher_preview_jobs import run as execute
    return execute(job_id)


@celery_app.task(name='app.tasks.matcher_preview.cleanup')
def cleanup():
    from app.services.matcher_preview_jobs import cleanup as execute
    return execute()


@celery_app.task(name='app.tasks.matcher_preview.recover')
def recover():
    from app.services.matcher_preview_jobs import recover as execute
    return execute()
