from celery import Celery

from app.core.config import get_settings

settings = get_settings()
celery_app = Celery(
    "ecommerce_operation_assistant",
    broker=settings.redis_url,
    backend=settings.celery_result_backend,
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    enable_utc=True,
    broker_connection_retry_on_startup=True,
    task_track_started=True,
    result_expires=3600,
    imports=["app.worker.tasks"],
)
