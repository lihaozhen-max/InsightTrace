FROM python:3.12-slim AS dependencies

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml ./
COPY app/__init__.py ./app/__init__.py
RUN pip install .


FROM dependencies AS test

RUN pip install ".[dev]"

COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic
COPY tests ./tests

CMD ["pytest", "-q"]


FROM dependencies AS runtime

COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic

RUN mkdir -p /app/storage/uploads /app/storage/exports /app/storage/workspace

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
