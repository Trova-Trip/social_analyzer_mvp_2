import os
from celery import Celery
from celery.schedules import crontab

# Configure Celery
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

celery_app = Celery(
    'social_analyzer',
    broker=REDIS_URL,
    backend=REDIS_URL
)

# Celery configuration
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='America/Los_Angeles',   # PST/PDT for beat schedule
    enable_utc=True,
    task_track_started=True,
    task_time_limit=600,  # 10 minutes max per task
    worker_prefetch_multiplier=1,  # Process one task at a time to avoid overwhelming OpenAI
    worker_max_tasks_per_child=50,  # Restart worker after 50 tasks to avoid memory leaks
)

# ── Celery Beat: scheduled tasks ──────────────────────────────────────────────
celery_app.conf.beat_schedule = {
    # Enrollment dispatcher — Mon–Fri at 9:00 AM PST (America/Los_Angeles)
    'enrollment-dispatcher-daily': {
        'task':     'tasks.run_enrollment_dispatcher',
        'schedule': crontab(hour=9, minute=0, day_of_week='1-5'),
    },
}

print(f"Celery configured with broker: {REDIS_URL}")
