FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/code

WORKDIR /code

COPY services/intelligence/graph-intelligence/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --requirement requirements.txt

COPY services/intelligence/graph-intelligence/stackgraph_graph_intelligence ./stackgraph_graph_intelligence
COPY services/intelligence/graph-intelligence/tests ./tests

ENTRYPOINT ["python", "-m", "stackgraph_graph_intelligence.worker"]
CMD ["serve"]
