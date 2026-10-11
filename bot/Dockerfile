FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml .
COPY app ./app
RUN pip install --no-cache-dir '.[test]' && useradd --uid 10001 --create-home food
COPY tests ./tests
USER food
CMD ["python", "-m", "app.main"]
