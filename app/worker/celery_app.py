from celery import Celery
from app.config import settings

celery_app = Celery(
    'job_bot',
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=['app.worker.tasks']
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Europe/Moscow',
    enable_utc=True,
    beat_schedule={  # можно задать здесь или в отдельном файле
        'parse-new-vacancies': {
            'task': 'app.worker.tasks.parse_new_vacancies_for_all_accounts',
            'schedule': settings.PARSE_INTERVAL * 60,  # в секундах
        },
        'check-invitations': {
            'task': 'app.worker.tasks.check_invitations_for_all_accounts',
            'schedule': settings.CHECK_INVITATIONS_INTERVAL * 60,
        },
    }
)