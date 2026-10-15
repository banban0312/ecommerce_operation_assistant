from app.worker.celery_app import celery_app


@celery_app.task(name="system.ping")
def ping() -> dict:
    """基础设施探针：仅验证 Worker 可执行任务，不调用模型或生成业务素材。"""
    return {"service": "worker", "status": "ok"}
