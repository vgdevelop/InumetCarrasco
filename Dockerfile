FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements-web.txt ./
COPY vendor/wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements-web.txt \
    && rm -rf /wheels \
    && addgroup --system tiempo \
    && adduser --system --ingroup tiempo tiempo

COPY weather ./weather
USER tiempo
EXPOSE 8000
CMD ["uvicorn", "weather.api:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
