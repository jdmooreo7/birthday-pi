# Birthday Pi app: one small Python container serving the monitor and phone pages.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BIRTHDAY_PI_DATA=/data

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY birthday_pi ./birthday_pi

# Run as a non-root user; /data holds the database (a named volume in compose.yaml).
RUN useradd --uid 1000 --create-home app && mkdir /data && chown app /data
USER app

EXPOSE 8080
HEALTHCHECK --interval=60s --timeout=5s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz')"
CMD ["uvicorn", "birthday_pi.main:app", "--host", "0.0.0.0", "--port", "8080"]
