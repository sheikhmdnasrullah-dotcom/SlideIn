FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY slidein-api/requirements.txt ./
RUN pip install --no-cache-dir --disable-pip-version-check -r requirements.txt

COPY slidein-api/slidein_api ./slidein_api
COPY product ./product

RUN useradd --create-home --uid 10001 slidein \
    && mkdir -p /app/data \
    && chown -R slidein:slidein /app

USER slidein
EXPOSE 8100

CMD ["python", "-m", "uvicorn", "slidein_api.api.app:app", "--host", "0.0.0.0", "--port", "8100"]
