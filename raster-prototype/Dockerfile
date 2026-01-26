FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

ENV PORT=8010
EXPOSE 8010

CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:8010", "app:app"]

