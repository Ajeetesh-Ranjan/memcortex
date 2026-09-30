# The client is deliberately dependency-free: standard library only, so there
# is no pip install step, no lockfile to drift, and no supply chain to audit.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    MEMCORTEX_HOST=0.0.0.0 \
    MEMCORTEX_PORT=8090

WORKDIR /app
COPY bin/ ./bin/
COPY dashboard/ ./dashboard/

# Non-root. The service only ever reads its own files and opens sockets.
RUN useradd --system --uid 10001 --no-create-home memcortex
USER memcortex

EXPOSE 8090

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
  CMD python3 -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8090/healthz',timeout=2).status==200 else 1)"

ENTRYPOINT ["python3", "bin/memcortex-client.py"]
