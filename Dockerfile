FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY dashboard.py .
COPY src/ ./src/
COPY web/ ./web/
COPY data/almora.geojson data/boundary-source.json data/firms-demo.json data/firms-demo.parquet data/power-almora.json ./data/

USER 10001:10001
EXPOSE 8080
CMD ["sh", "-c", "exec python -m waitress --listen=0.0.0.0:${PORT:-8080} dashboard:app"]
