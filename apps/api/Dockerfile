FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/code

WORKDIR /code

COPY requirements.txt ./
RUN pip install --no-cache-dir --requirement requirements.txt

FROM base AS development

COPY requirements-dev.txt ./
RUN pip install --no-cache-dir --requirement requirements-dev.txt

COPY app ./app
COPY tests ./tests

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

FROM base AS runtime

RUN addgroup --system stackgraph \
    && adduser --system --ingroup stackgraph --home /nonexistent --no-create-home stackgraph

COPY --chown=stackgraph:stackgraph app ./app

USER stackgraph

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
