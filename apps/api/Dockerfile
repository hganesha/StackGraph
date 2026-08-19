FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/code

WORKDIR /code

COPY apps/api/requirements.txt ./
RUN pip install --no-cache-dir --requirement requirements.txt

FROM base AS development

COPY apps/api/requirements-dev.txt ./
RUN pip install --no-cache-dir --requirement requirements-dev.txt

COPY apps/api/app ./app
COPY apps/api/tests ./tests
COPY services/intelligence/ai-services/stackgraph_ai ./stackgraph_ai
COPY services/intelligence/ai-services/prompts ./prompts

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

FROM base AS runtime

RUN addgroup --system stackgraph \
    && adduser --system --ingroup stackgraph --home /nonexistent --no-create-home stackgraph

COPY --chown=stackgraph:stackgraph apps/api/app ./app
COPY --chown=stackgraph:stackgraph services/intelligence/ai-services/stackgraph_ai ./stackgraph_ai
COPY --chown=stackgraph:stackgraph services/intelligence/ai-services/prompts ./prompts

USER stackgraph

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
