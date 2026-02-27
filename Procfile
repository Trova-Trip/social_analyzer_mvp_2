web: gunicorn wsgi:app --bind 0.0.0.0:$PORT --timeout 600 --workers 2
worker: rq worker-pool --num-workers 4 --with-scheduler --url $REDIS_URL
