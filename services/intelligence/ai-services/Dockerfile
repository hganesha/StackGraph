FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/code

WORKDIR /code
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY stackgraph_ai ./stackgraph_ai
COPY prompts ./prompts
COPY tests ./tests

ENTRYPOINT ["python", "-m", "stackgraph_ai.sync_prompts"]
