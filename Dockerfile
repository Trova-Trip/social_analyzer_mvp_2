FROM python:3.13-slim

WORKDIR /app

# Install postgres client (for pg_isready in healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

CMD ["gunicorn", "wsgi:app", "--bind", "0.0.0.0:8080", "--timeout", "600", "--workers", "2"]
