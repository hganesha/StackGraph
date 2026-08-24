# Build from the repository root so the frozen OpenAPI contract ships in the image.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/code \
    STACKGRAPH_MCP_OPENAPI_PATH=/contracts/v1/openapi.json

WORKDIR /code

COPY services/mcp-server/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --requirement requirements.txt

COPY services/mcp-server/stackgraph_mcp ./stackgraph_mcp
COPY stackgraph-foundation/contracts/v1 /contracts/v1

ENTRYPOINT ["python", "-m", "stackgraph_mcp"]
CMD ["--transport", "http", "--host", "0.0.0.0", "--port", "8081"]
