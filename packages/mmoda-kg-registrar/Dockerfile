FROM python:3.13-slim-trixie

# Python deps
COPY . /app
RUN pip install --no-cache-dir /app

WORKDIR /data

CMD ["mmoda-kg-registrar", "--host", "0.0.0.0", "--port", "8181"]