FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /service

COPY stackgraph_discovery ./stackgraph_discovery

ENTRYPOINT ["python", "-m", "stackgraph_discovery.github_snapshot"]
