FROM ghcr.io/astral-sh/uv:python3.13-trixie-slim AS builder

# Python deps
ENV UV_NO_DEV=1
ENV UV_LINK_MODE=copy
ENV UV_PYTHON_DOWNLOADS=0

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl git

ARG HELM_VERSION=v4.1.4

ENV HELM_PLUGINS=/app/helm-plugins

RUN <<EOF
curl -O https://get.helm.sh/helm-${HELM_VERSION}-linux-amd64.tar.gz
curl -O https://get.helm.sh/helm-${HELM_VERSION}-linux-amd64.tar.gz.sha256sum
sha256sum -c helm-${HELM_VERSION}-linux-amd64.tar.gz.sha256sum
tar xzf helm-${HELM_VERSION}-linux-amd64.tar.gz
./linux-amd64/helm plugin install https://github.com/databus23/helm-diff --verify=false
EOF


RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --no-install-project --no-editable

COPY . /app

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-editable

FROM python:3.13-slim-trixie

ENV HELM_PLUGINS=/usr/local/share/helm/plugins

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/linux-amd64/helm /usr/local/bin/helm
COPY --from=builder /app/helm-plugins /usr/local/share/helm/plugins

CMD ["/app/.venv/bin/mmodabot"]  
# override to pass config