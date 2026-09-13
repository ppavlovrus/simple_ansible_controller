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
#   BASE_IMAGE=ubuntu:24.04 packaging/build-deb.sh
#
# The base image decides which python the virtualenv is built against, and a
# virtualenv only works with the python minor version that built it. The
# dependency in the control file is generated to match, so the package refuses
# to install where it would not run rather than installing and failing at the
# first start. Build one per distribution you support.
#
# The result lands in dist/.
set -euo pipefail

ARCHITECTURE="${1:-amd64}"
BASE_IMAGE="${BASE_IMAGE:-debian:bookworm-slim}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(sed -n 's/^version = "\(.*\)"/\1/p' "$ROOT/pyproject.toml" | head -1)"
RUNTIME="$(command -v docker || command -v podman)"

if [[ -z "$RUNTIME" ]]; then
    echo "build-deb: needs docker or podman to build on the target platform" >&2
    exit 2
fi

echo "building ansible-mcp ${VERSION} for ${ARCHITECTURE} on ${BASE_IMAGE}"

"$RUNTIME" run --rm \
    --platform "linux/${ARCHITECTURE}" \
    --volume "$ROOT:/src:ro" \
    --volume "$ROOT/dist:/out" \
    --workdir /build \
    "$BASE_IMAGE" \
    bash -euo pipefail -c '
        export DEBIAN_FRONTEND=noninteractive
        apt-get update >/dev/null
        apt-get install --no-install-recommends --yes \
            python3 python3-venv python3-pip dpkg-dev >/dev/null

        VERSION="'"$VERSION"'"
        ARCHITECTURE="'"$ARCHITECTURE"'"
        STAGE=/build/stage

        # A virtualenv is bound to the python minor version that created it:
        # its site-packages lives under lib/pythonX.Y, and another interpreter
        # does not look there. Installing on a distribution with a different
        # python therefore produces a service that starts and immediately dies
        # on "No module named ansible_mcp" -- found by installing a bookworm
        # package on Ubuntu 24.04. The control file below pins what this build
        # actually produced.
        PYTHON_VERSION=$(python3 -c "import sys; print(f\"{sys.version_info.major}.{sys.version_info.minor}\")")
        PYTHON_NEXT=$(python3 -c "import sys; print(f\"{sys.version_info.major}.{sys.version_info.minor + 1}\")")

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

        # Shipped, not enabled: the drop-in weakens the unit confinement, and
        # only an installation that isolates runs should take that trade.
        mkdir -p "$STAGE/usr/share/ansible-mcp/systemd"
        cp /src/packaging/systemd/isolation.conf "$STAGE/usr/share/ansible-mcp/systemd/"

        INSTALLED_SIZE=$(du -sk "$STAGE" | cut -f1)
        mkdir -p "$STAGE/DEBIAN"
        cat > "$STAGE/DEBIAN/control" <<CONTROL
Package: ansible-mcp
Version: ${VERSION}
Section: admin
Priority: optional
Architecture: ${ARCHITECTURE}
Depends: python3 (>= ${PYTHON_VERSION}), python3 (<< ${PYTHON_NEXT}), openssh-client
Recommends: sshpass
Suggests: podman
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

    # Subordinate id ranges, so rootless podman can map ids inside a container
    # if this installation ever turns isolation on (ADR-0016). Registering them
    # costs a line in a file and nothing at runtime. An existing entry is left
    # alone, and a new range starts past everything already allocated, because
    # two users sharing a range is two users sharing an identity.
    # Podman talks to a systemd user session by default, and a system user has
    # none: it falls back correctly but warns twice on stderr, and that stderr
    # is what a caller reads back as the output of a syntax check. Written only
    # if absent, so an operator who configured podman keeps their settings.
    CONTAINERS_CONF=/var/lib/ansible-mcp/.config/containers/containers.conf
    if [ ! -e "$CONTAINERS_CONF" ]; then
        mkdir -p /var/lib/ansible-mcp/.config/containers
        printf "[engine]\ncgroup_manager = \"cgroupfs\"\n" > "$CONTAINERS_CONF"
        chown -R ansible-mcp:ansible-mcp /var/lib/ansible-mcp/.config
    fi

    for IDFILE in /etc/subuid /etc/subgid; do
        [ -e "$IDFILE" ] || : > "$IDFILE"
        if ! grep -q "^ansible-mcp:" "$IDFILE"; then
            START=$(awk -F: "BEGIN { top = 100000 }
                             { end = \$2 + \$3; if (end > top) top = end }
                             END { print top }" "$IDFILE")
            echo "ansible-mcp:${START}:65536" >> "$IDFILE"
        fi
    done
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
