FROM python:3.12-slim

WORKDIR /app

# ripgrep for fallback grep, git for cloning the target project repo.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ripgrep git \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps before copying source so this layer is cached.
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app/dual-graph-dashboard

ENV PYTHONUNBUFFERED=1
# Dashboard API runs internally on 8787; MCP SSE uses Railway's PORT.
ENV DG_BASE_URL=http://127.0.0.1:8787

RUN chmod +x /app/dual-graph-dashboard/start.sh

# Optional env vars (set in Railway dashboard):
#   GITHUB_REPO_URL    – repo to clone as the target project
#   GITHUB_TOKEN       – personal access token for private repos
#   DG_API_TOKEN       – bearer token to protect the dashboard API
#   DUAL_GRAPH_PROJECT_ROOT – overrides the default clone path (/app/project)

CMD ["/app/dual-graph-dashboard/start.sh"]
