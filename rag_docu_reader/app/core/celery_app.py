from celery import Celery
from app.core.config import settings

ssl_kwargs = {"ssl_cert_reqs": "none"} if settings.REDIS_URL.startswith("rediss://") else None

celery_app = Celery(
    "worker",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    broker_use_ssl=ssl_kwargs,
    redis_backend_use_ssl=ssl_kwargs,
    include=["app.services.tasks"]
)

celery_app.conf.task_routes = {"app.services.tasks.*": "main-queue"}
