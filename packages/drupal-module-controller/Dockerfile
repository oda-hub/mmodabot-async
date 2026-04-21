FROM ghcr.io/oda-hub/frontend-container:44abab3-260421084135

RUN curl -LsSf https://astral.sh/uv/0.11.7/install.sh | sh
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Python deps
COPY . /app
WORKDIR /app

RUN $HOME/.local/bin/uv sync --python 3.13 --no-cache

ENTRYPOINT [ "uv", "run" ]
CMD ["mmoda-drupal-module-controller", "--host", "0.0.0.0", "--port", "8181"]