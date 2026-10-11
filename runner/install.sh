#!/bin/sh
# Installs the Codex runner on the VPS. Run as root from this directory:
#   sudo sh install.sh "ssh-ed25519 AAAA... food-tracker@home-server"
# Creates the system user food-ai, installs the runner as the only command its SSH key
# may run, and puts the Codex config into the runner's own CODEX_HOME.
set -eu

KEY=${1:-}
RUNNER_USER=${RUNNER_USER:-food-ai}
HOME_DIR=/var/lib/$RUNNER_USER

if ! id "$RUNNER_USER" >/dev/null 2>&1; then
    useradd --system --create-home --home-dir "$HOME_DIR" --shell /bin/bash "$RUNNER_USER"
fi

install -m 0755 food_codex_runner.py /usr/local/bin/food-codex-runner
install -d -m 0700 -o "$RUNNER_USER" -g "$RUNNER_USER" \
    "$HOME_DIR/.ssh" "$HOME_DIR/codex-home" "$HOME_DIR/work"
if [ ! -f "$HOME_DIR/codex-home/config.toml" ]; then
    install -m 0600 -o "$RUNNER_USER" -g "$RUNNER_USER" codex-config.toml \
        "$HOME_DIR/codex-home/config.toml"
fi

if [ -n "$KEY" ]; then
    # restrict: no port forwarding, agent, X11 or pty; command: the runner and nothing else.
    printf 'restrict,command="/usr/local/bin/food-codex-runner" %s\n' "$KEY" \
        > "$HOME_DIR/.ssh/authorized_keys"
    chown "$RUNNER_USER:$RUNNER_USER" "$HOME_DIR/.ssh/authorized_keys"
    chmod 0600 "$HOME_DIR/.ssh/authorized_keys"
fi

if ! command -v codex >/dev/null 2>&1; then
    echo "Codex CLI is not installed yet: npm install -g @openai/codex (Node.js 22+)."
fi
echo "Next: sudo -iu $RUNNER_USER env CODEX_HOME=$HOME_DIR/codex-home codex login --device-auth"
