FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/code

WORKDIR /code

COPY requirements.txt ./
RUN pip install --no-cache-dir --requirement requirements.txt

COPY stackgraph_data ./stackgraph_data
COPY tests ./tests

CMD ["python", "-m", "stackgraph_data.seed"]
