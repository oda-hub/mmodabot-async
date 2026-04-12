FROM ghcr.io/astral-sh/uv:python3.13-trixie-slim AS builder

# Python deps
ENV UV_NO_DEV=1
ENV UV_LINK_MODE=copy
ENV UV_PYTHON_DOWNLOADS=0

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl git

ARG HELM_VERSION=v4.1.4

RUN <<EOF
curl -O https://get.helm.sh/helm-${HELM_VERSION}-linux-amd64.tar.gz
curl -O https://get.helm.sh/helm-${HELM_VERSION}-linux-amd64.tar.gz.sha256sum
sha256sum -c helm-${HELM_VERSION}-linux-amd64.tar.gz.sha256sum
tar xzf helm-${HELM_VERSION}-linux-amd64.tar.gz
mv ./linux-amd64/helm /usr/local/bin/helm
helm plugin install https://github.com/databus23/helm-diff --verify=false
EOF


RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --no-install-project --no-editable

COPY . /app

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-editable

ENV TINI_VERSION=v0.19.0
RUN curl -o /tini https://github.com/krallin/tini/releases/download/${TINI_VERSION}/tini
RUN chmod +x /tini


FROM python:3.13-slim-trixie

# nb2workflow needs git cli
RUN apt-get update && apt-get install -y --no-install-recommends git && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN useradd -u 1000 -U -m bot

COPY --from=builder /tini /tini
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /usr/local/bin/helm /usr/local/bin/helm
COPY --from=builder --chown=1000:1000 /root/.cache/helm /home/bot/.cache/helm
COPY --from=builder --chown=1000:1000 /root/.local/share/helm /home/bot/.local/share/helm

USER 1000
WORKDIR /tmp

ENTRYPOINT ["/tini", "--"]

CMD ["/app/.venv/bin/mmodabot"]  
