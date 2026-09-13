# The whole product in one image: a process, a volume, a port.
#
#   docker build -f Containerfile -t ansible-mcp .
#   docker run -p 8080:8080 -v ./data:/data -e ANSIBLE_MCP_API_KEY=... ansible-mcp
#
# The key is not optional: the container binds beyond loopback, and the server
# refuses to serve an unauthenticated endpoint (ADR-0012).
#
# Two stages. The builder resolves everything into a self-contained virtualenv;
# the runtime copies that virtualenv and nothing else, so Poetry, the wheel, the
# sources and pip's cache never reach the shipped image.

FROM python:3.14-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore

# Poetry goes into the image's own python, deliberately before the virtualenv
# is put on PATH: installed after, it lands inside /opt/venv and is copied into
# the runtime with everything it drags along -- which is what this file used to
# do, to the tune of 22MB and a `poetry` on the shipped PATH.
RUN pip install "poetry>=2.0"

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /src

# Copied before the sources so a dependency-only change reuses this layer.
COPY pyproject.toml poetry.lock README.md ./
COPY src ./src
RUN poetry build --format wheel

# --no-compile leaves out the .pyc files, which are a third of the installed
# weight and are rebuilt in memory on first import anyway. Then the packaging
# tools and ansible's own test suite go: nothing in the runtime installs or
# tests anything.
RUN pip install --no-compile ./dist/*.whl \
    && pip uninstall --yes pip setuptools wheel 2>/dev/null || true
RUN rm -rf /opt/venv/lib/python3.11/site-packages/ansible_test \
    && find /opt/venv -name "__pycache__" -type d -prune -exec rm -rf {} + \
    && find /opt/venv -name "*.dist-info" -type d -exec rm -rf {}/RECORD \;


FROM python:3.14-slim AS runtime

# ansible-runner shells out to ansible-playbook, which reaches hosts over SSH.
# sshpass is what Ansible needs when an inventory authenticates with a password
# rather than a key; the alternative is a runtime that cannot connect.
RUN apt-get update \
    && apt-get install --no-install-recommends --yes openssh-client sshpass \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv

# Runs unprivileged: this process executes playbooks, so root inside the
# container buys nothing and costs everything if the endpoint is reached.
RUN useradd --system --uid 1000 --create-home --home-dir /var/lib/ansible-mcp ansible-mcp \
    && mkdir -p /data/inventories \
    && chown -R ansible-mcp:ansible-mcp /data

USER ansible-mcp
WORKDIR /var/lib/ansible-mcp

ENV PATH="/opt/venv/bin:$PATH" \
    ANSIBLE_MCP_DATA_DIR=/data \
    ANSIBLE_MCP_HOST=0.0.0.0 \
    ANSIBLE_MCP_PORT=8080 \
    ANSIBLE_MCP_TRANSPORT=streamable-http \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8080
VOLUME ["/data"]

# /healthz needs no token, which is why it can be the probe.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request as r, sys; sys.exit(0 if r.urlopen('http://127.0.0.1:8080/healthz', timeout=3).status == 200 else 1)"

ENTRYPOINT ["ansible-mcp"]
