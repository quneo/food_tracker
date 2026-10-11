FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
# ssh: the assistant runs on the VPS behind an SSH forced command (see runner/).
RUN apt-get update && apt-get install -y --no-install-recommends openssh-client \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml .
COPY app ./app
RUN pip install --no-cache-dir '.[test]' \
    && useradd --uid 10001 --create-home food && mkdir /data && chown food:food /data
COPY alembic.ini .
COPY alembic ./alembic
COPY tests ./tests
USER food
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
