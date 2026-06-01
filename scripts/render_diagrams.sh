#!/usr/bin/env bash
# Render the Mermaid diagram sources (diagrams/*.md) to SVG using mermaid-cli in
# Docker. Markdown inputs with multiple ```mermaid blocks produce <name>-N.svg.
set -euo pipefail

REPO="${HOST_REPO_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
DIAG="$REPO/diagrams"
IMAGE="${MERMAID_IMAGE:-minlag/mermaid-cli:latest}"

# Chromium needs --no-sandbox inside the container.
cat > "$DIAG/.puppeteer.json" <<'JSON'
{ "args": ["--no-sandbox", "--disable-setuid-sandbox"] }
JSON

for f in 01_data_model 02_temporal_workflows 03_langgraph_agent; do
  echo "[diagrams] rendering $f.md"
  docker run --rm -v "$DIAG":/data "$IMAGE" \
    -i "/data/$f.md" -o "/data/$f.svg" \
    -p /data/.puppeteer.json -b transparent -t neutral
done
echo "[diagrams] done — see diagrams/*.svg"
