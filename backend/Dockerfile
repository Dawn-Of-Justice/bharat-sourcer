FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml requirements-dev.lock ./
COPY src ./src
RUN pip install --no-cache-dir -r requirements-dev.lock . && useradd --uid 10001 --create-home appuser
USER appuser
ENV PORT=8080
CMD ["sh", "-c", "exec uvicorn bharat_sourcer.main:app --host 0.0.0.0 --port ${PORT} --workers 1"]
