from app.worker.celery_app import celery_app


@celery_app.task(name="system.ping")
def ping() -> dict:
    """Infrastructure probe; does not call models or create business assets."""
    return {"service": "worker", "status": "ok"}
