FROM mirror.gcr.io/library/python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
# Pango and a font with the rupee sign for WeasyPrint (PDF export).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 \
        libharfbuzz-subset0 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml requirements-dev.lock ./
COPY src ./src
RUN pip install --no-cache-dir -r requirements-dev.lock . && useradd --uid 10001 --create-home appuser
USER appuser
ENV PORT=8080
CMD ["sh", "-c", "exec uvicorn bharat_sourcer.main:app --host 0.0.0.0 --port ${PORT} --workers 1"]
