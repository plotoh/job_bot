from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery(
    'job_bot',
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=['app.worker.tasks']
)
#
# celery_app.conf.beat_schedule = {
#     'parse-all-vacancies': {
#         'task': 'app.worker.tasks.parse_all_vacancies',
#         'schedule': settings.PARSE_INTERVAL * 60,  # например, раз в 60 минут
#     },
#     'generate-and-send-responses': {
#         'task': 'app.worker.tasks.generate_and_send_responses',
#         'schedule': 30 * 60,  # каждые 30 минут
#     },
#     'reset-daily-limits': {
#         'task': 'app.worker.tasks.reset_daily_limits',
#         'schedule': 24 * 60 * 60,  # раз в сутки (в полночь по серверу)
#     },
# }

celery_app.conf.beat_schedule = {
    'parse-all-vacancies-daily': {
        'task': 'app.worker.tasks.parse_all_vacancies',
        'schedule': crontab(hour=8, minute=0),  # каждый день в 8:00
    },
    'generate-and-send-responses': {
        'task': 'app.worker.tasks.generate_and_send_responses',
        'schedule': 30 * 60,  # каждые 30 минут
    },
    'reset-daily-limits': {
        'task': 'app.worker.tasks.reset_daily_limits',
        'schedule': crontab(hour=0, minute=0),  # каждый день в полночь
    },
}
