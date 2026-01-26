FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install Python deps first (better Docker layer caching)
COPY backend-api-test/backend/requirements.txt /app/backend-api-test/backend/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/backend-api-test/backend/requirements.txt

# Copy application
COPY . /app

WORKDIR /app/backend-api-test/backend

ENV PORT=8000
EXPOSE 8000

# Production server
CMD ["gunicorn", "-w", "2", "-k", "gthread", "--threads", "4", "-b", "0.0.0.0:8000", "app:app"]

