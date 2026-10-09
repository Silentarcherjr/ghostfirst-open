# GhostFirst MCP server over Streamable HTTP, plus the voice simulator at /.
#
#   docker build -t ghostfirst-mcp .
#   docker run -p 127.0.0.1:8780:8780 -e MCP_HOSTNAME=mcp.example.org ghostfirst-mcp
#
# Put a TLS proxy in front; MCP_HOSTNAME is the public host name it serves.
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/tmp

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir . \
    && useradd --no-create-home --shell /usr/sbin/nologin ghostfirst

USER ghostfirst
EXPOSE 8780
CMD ["sh", "-c", "exec ghostfirst-mcp --http --host 0.0.0.0 --port 8780 --allowed-host \"${MCP_HOSTNAME:?set MCP_HOSTNAME}\""]
