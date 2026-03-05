# app/worker/celery_app.py
from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery(
    'job_bot',
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=['app.worker.tasks']
)

celery_app.conf.beat_schedule = {
    'parse-all-vacancies-daily': {
        'task': 'app.worker.tasks.parse_all_vacancies',
        'schedule': crontab(hour=8, minute=0),
    },
    'generate-and-send-responses': {
        'task': 'app.worker.tasks.generate_and_send_responses',
        'schedule': 30 * 60,
    },
    'reset-daily-limits': {
        'task': 'app.worker.tasks.reset_daily_limits',
        'schedule': crontab(hour=0, minute=0),
    },
    'refresh-all-cookies': {
        'task': 'app.worker.tasks.refresh_all_cookies',
        'schedule': crontab(minute=0, hour='*/12'),
    },
}
