# syntax=docker/dockerfile:1.7

FROM python:3.12-slim AS dependencies

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin app

COPY requirements.txt ./requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    python -m pip install --no-warn-script-location -r requirements.txt

FROM dependencies AS runtime

COPY --chown=10001:10001 app ./app

USER 10001:10001
EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]

FROM runtime AS test

USER root
COPY requirements-dev.txt ./requirements-dev.txt
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    python -m pip install --no-warn-script-location -r requirements-dev.txt
COPY --chown=10001:10001 tests ./tests

USER 10001:10001
CMD ["python", "-m", "pytest", "tests", "-q"]
