#!/usr/bin/env bash
# Build a .deb that installs the service into /opt/ansible-mcp.
#
# The package carries its own virtualenv, because its dependencies (the MCP SDK,
# ansible-runner) are not in distribution repositories. That virtualenv holds
# compiled wheels, so it has to be built on the target platform: the build runs
# inside a Debian container rather than on whatever machine invokes this.
#
#   packaging/build-deb.sh            # amd64, needs docker or podman
#   packaging/build-deb.sh arm64
#
# The result lands in dist/.
set -euo pipefail

ARCHITECTURE="${1:-amd64}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(sed -n 's/^version = "\(.*\)"/\1/p' "$ROOT/pyproject.toml" | head -1)"
RUNTIME="$(command -v docker || command -v podman)"

if [[ -z "$RUNTIME" ]]; then
    echo "build-deb: needs docker or podman to build on the target platform" >&2
    exit 2
fi

echo "building ansible-mcp ${VERSION} for ${ARCHITECTURE}"

"$RUNTIME" run --rm \
    --platform "linux/${ARCHITECTURE}" \
    --volume "$ROOT:/src:ro" \
    --volume "$ROOT/dist:/out" \
    --workdir /build \
    debian:bookworm-slim \
    bash -euo pipefail -c '
        export DEBIAN_FRONTEND=noninteractive
        apt-get update >/dev/null
        apt-get install --no-install-recommends --yes \
            python3 python3-venv python3-pip dpkg-dev >/dev/null

        VERSION="'"$VERSION"'"
        ARCHITECTURE="'"$ARCHITECTURE"'"
        STAGE=/build/stage

        # Built at the path it will be installed to, then copied into the
        # staging tree. A virtualenv is not relocatable: the console scripts get
        # an absolute shebang, so one built under the staging prefix would ship
        # pointing at a directory that only existed on the build machine.
        python3 -m venv /opt/ansible-mcp/venv
        /opt/ansible-mcp/venv/bin/pip install --no-cache-dir --quiet --upgrade pip wheel
        /opt/ansible-mcp/venv/bin/pip install --no-cache-dir --quiet /src

        # Nothing installs packages at runtime.
        /opt/ansible-mcp/venv/bin/pip uninstall --yes --quiet pip wheel setuptools 2>/dev/null || true
        find /opt/ansible-mcp/venv -name "__pycache__" -type d -prune -exec rm -rf {} + || true

        mkdir -p "$STAGE/opt/ansible-mcp"
        cp -a /opt/ansible-mcp/venv "$STAGE/opt/ansible-mcp/venv"

        # /var/lib/ansible-mcp is created by postinst on purpose: a directory
        # owned by the package is deleted on remove, and it holds the task
        # history and the stored playbooks.
        mkdir -p "$STAGE/lib/systemd/system" "$STAGE/etc/ansible-mcp"
        cp /src/packaging/systemd/ansible-mcp.service "$STAGE/lib/systemd/system/"
        cp /src/packaging/debian/ansible-mcp.env "$STAGE/etc/ansible-mcp/"

        INSTALLED_SIZE=$(du -sk "$STAGE" | cut -f1)
        mkdir -p "$STAGE/DEBIAN"
        cat > "$STAGE/DEBIAN/control" <<CONTROL
Package: ansible-mcp
Version: ${VERSION}
Section: admin
Priority: optional
Architecture: ${ARCHITECTURE}
Depends: python3 (>= 3.11), openssh-client
Recommends: sshpass
Installed-Size: ${INSTALLED_SIZE}
Maintainer: ansible-mcp maintainers <noreply@example.invalid>
Description: Minimal Ansible controller with an MCP interface
 Runs Ansible playbooks on request and keeps their history, logs and
 artifacts. The primary interface is MCP, so an AI agent can drive it
 directly; a REST surface exists for scripts and humans.
 .
 State lives in SQLite under /var/lib/ansible-mcp. No database server,
 message broker or worker fleet is required.
CONTROL

        cat > "$STAGE/DEBIAN/conffiles" <<CONFFILES
/etc/ansible-mcp/ansible-mcp.env
CONFFILES

        cat > "$STAGE/DEBIAN/postinst" <<"POSTINST"
#!/bin/sh
set -e

if [ "$1" = "configure" ]; then
    if ! getent passwd ansible-mcp >/dev/null; then
        adduser --system --group --no-create-home \
            --home /var/lib/ansible-mcp \
            --gecos "Ansible MCP controller" ansible-mcp
    fi

    mkdir -p /var/lib/ansible-mcp/inventories
    chown -R ansible-mcp:ansible-mcp /var/lib/ansible-mcp
    # The env file may hold an API key, so it is readable by the service only.
    chown root:ansible-mcp /etc/ansible-mcp/ansible-mcp.env
    chmod 640 /etc/ansible-mcp/ansible-mcp.env

    if [ -d /run/systemd/system ]; then
        systemctl daemon-reload
        echo "ansible-mcp: set ANSIBLE_MCP_API_KEY in /etc/ansible-mcp/ansible-mcp.env,"
        echo "             then: systemctl enable --now ansible-mcp"
    fi
fi
POSTINST
        chmod 755 "$STAGE/DEBIAN/postinst"

        cat > "$STAGE/DEBIAN/postrm" <<"POSTRM"
#!/bin/sh
set -e
# Files the interpreter writes after installation (bytecode caches) are not
# owned by the package, so dpkg leaves the tree behind without this.
if [ "$1" = "remove" ] || [ "$1" = "purge" ]; then
    rm -rf /opt/ansible-mcp
fi
# State is deliberately kept on remove and dropped only on purge: it holds the
# task history and the stored playbooks.
if [ "$1" = "purge" ]; then
    rm -rf /var/lib/ansible-mcp /etc/ansible-mcp
    if getent passwd ansible-mcp >/dev/null; then
        deluser --system ansible-mcp >/dev/null 2>&1 || true
    fi
fi
POSTRM
        chmod 755 "$STAGE/DEBIAN/postrm"

        cat > "$STAGE/DEBIAN/prerm" <<"PRERM"
#!/bin/sh
set -e
if [ -d /run/systemd/system ] && [ "$1" = "remove" ]; then
    systemctl stop ansible-mcp >/dev/null 2>&1 || true
    systemctl disable ansible-mcp >/dev/null 2>&1 || true
fi
PRERM
        chmod 755 "$STAGE/DEBIAN/prerm"

        dpkg-deb --root-owner-group --build "$STAGE" \
            "/out/ansible-mcp_${VERSION}_${ARCHITECTURE}.deb"
        chmod a+r "/out/ansible-mcp_${VERSION}_${ARCHITECTURE}.deb"
    '

echo "built dist/ansible-mcp_${VERSION}_${ARCHITECTURE}.deb"
