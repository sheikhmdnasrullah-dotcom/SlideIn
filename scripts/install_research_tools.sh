#!/usr/bin/env bash
# Install every review-approved research/runtime tool and fail on any absence.
set -euo pipefail

ROOT="${1:-/opt/slidein}"
VENV="$ROOT/research-venv"
TOOLS="$ROOT/research-tools"
UV_BIN="/root/.local/bin/uv"
AGENT_REACH_ZIP="https://github.com/Panniantong/Agent-Reach/releases/latest/download/agent-reach.zip"
BLACKBIRD_REPO="https://github.com/p1ngul1n0/blackbird.git"

log() { echo "==> research: $*"; }
die() { echo "ERROR: research tools incomplete: $*" >&2; exit 1; }

mkdir -p "$VENV" "$TOOLS" /usr/local/bin
python3 -m venv "$VENV"
PIP="$VENV/bin/pip"

log "installing Python research tools"
"$PIP" install --no-cache-dir -q \
  openosint \
  spider_rs \
  crawl4ai \
  theHarvester \
  holehe \
  maigret \
  sherlock-project \
  botasaurus

log "installing browser runtime"
"$VENV/bin/playwright" install --with-deps chromium

log "installing Agent Reach from its official release"
if [ ! -x "$UV_BIN" ]; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
"$UV_BIN" tool install --force "$AGENT_REACH_ZIP"
/root/.local/bin/agent-reach setup

log "installing Blackbird as a separately licensed external CLI"
if [ ! -d "$TOOLS/blackbird/.git" ]; then
  git clone --depth 1 "$BLACKBIRD_REPO" "$TOOLS/blackbird"
else
  git -C "$TOOLS/blackbird" pull --ff-only
fi
"$PIP" install --no-cache-dir -q -r "$TOOLS/blackbird/requirements.txt"
cat > /usr/local/bin/blackbird <<'WRAPPER'
#!/usr/bin/env bash
exec /opt/slidein/research-venv/bin/python /opt/slidein/research-tools/blackbird/blackbird.py "$@"
WRAPPER
chmod 0755 /usr/local/bin/blackbird

for command_name in openosint theHarvester holehe maigret sherlock crawl4ai; do
  if [ -x "$VENV/bin/$command_name" ] && [ ! -e "/usr/local/bin/$command_name" ]; then
    ln -s "$VENV/bin/$command_name" "/usr/local/bin/$command_name"
  fi
done

python3 - <<'PYCHECK'
import importlib.util
missing = [name for name in ("spider_rs",) if importlib.util.find_spec(name) is None]
if missing:
    raise SystemExit("missing Python modules: " + ", ".join(missing))
PYCHECK

command -v openosint >/dev/null || die "openosint command missing"
command -v agent-reach >/dev/null || die "agent-reach command missing"
command -v blackbird >/dev/null || die "blackbird command missing"
command -v theHarvester >/dev/null || die "theHarvester command missing"
command -v holehe >/dev/null || die "holehe command missing"
command -v maigret >/dev/null || die "maigret command missing"
command -v sherlock >/dev/null || die "sherlock command missing"
command -v crawl4ai >/dev/null || die "crawl4ai command missing"
"$VENV/bin/python" -c 'import spider_rs' || die "spider_rs import failed"
"$VENV/bin/python" -m playwright --version >/dev/null || die "Playwright browser runtime missing"

echo "research tools installed and smoke-checked"
