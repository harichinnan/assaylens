FROM python:3.11-slim

# psql for ad-hoc verification; the Docker CLI so Temporal activities can launch
# the lakehouse job containers (Bronze sbt job, dbt-spark, Spark publisher) via
# the mounted host Docker socket (docker-out-of-docker). bash/git for scripts.
ARG DOCKER_CLI_VERSION=26.1.4
RUN apt-get update && apt-get install -y --no-install-recommends \
      postgresql-client bash git curl ca-certificates && \
    arch="$(uname -m)" && \
    curl -fsSL "https://download.docker.com/linux/static/stable/${arch}/docker-${DOCKER_CLI_VERSION}.tgz" \
      | tar -xz --strip-components=1 -C /usr/local/bin docker/docker && \
    apt-get purge -y curl && apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY orchestration/requirements.txt /tmp/req.txt
RUN pip install --no-cache-dir -r /tmp/req.txt

# The repository is bind-mounted at /app at runtime via docker-compose, so code
# changes need no rebuild. Lakehouse job containers are launched by the activities
# via `docker run` (the run_*.sh scripts), using HOST_REPO_DIR for host-correct
# bind-mount paths.
CMD ["python", "-m", "orchestration.worker"]
