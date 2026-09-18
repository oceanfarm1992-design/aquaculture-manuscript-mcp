FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src/ ./src/

RUN pip install --no-cache-dir .

# stdio is the default and correct transport for local MCP clients; set
# AQUA_TRANSPORT=sse or streamable-http when running this container as a
# remote server. AQUA_API_KEY / AQUA_BASE_URL / AQUA_MODEL are only needed
# if you use run_agent_with_external_model or run_pipeline.
ENV AQUA_TRANSPORT=stdio

ENTRYPOINT ["aquaculture-manuscript-mcp"]
