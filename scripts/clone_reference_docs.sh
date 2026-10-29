#!/usr/bin/env bash
# Complete documentation of the tools baseballpy uses and the projects it is compared with:
# shallow clones of their own repositories (docs included), kept OUTSIDE this repository.
# Run on the homelab (disk): bash scripts/clone_reference_docs.sh [DEST]   (default ~/reference-docs)
set -euo pipefail
DEST="${1:-$HOME/reference-docs}"
mkdir -p "$DEST"
cd "$DEST"
REPOS=(
  dlt-hub/dlt pola-rs/polars duckdb/duckdb-web apache/arrow narwhals-dev/narwhals
  jcrist/msgspec encode/httpx pydantic/pydantic pydantic/pydantic-settings jd/tenacity
  mjpieters/aiolimiter Textualize/rich pallets/click lundberg/respx
  HypothesisWorks/hypothesis pytest-dev/pytest
  jldbc/pybaseball BillPetti/baseballr toddrob99/MLB-StatsAPI zero-sum-seattle/python-mlb-statsapi
  droher/boxball droher/baseball.computer chadwickbureau/chadwick chadwickbureau/retrosheet
)
for repo in "${REPOS[@]}"; do
  name="${repo##*/}"
  if [ -d "$name/.git" ]; then git -C "$name" pull --ff-only -q || echo "pull failed: $repo"
  else git clone --depth 1 -q "https://github.com/$repo.git" "$name" || echo "clone failed: $repo"; fi
done
for d in */; do printf '%s %s %s\n' "${d%/}" "$(git -C "$d" rev-parse --short HEAD 2>/dev/null)" "$(du -sh "$d" | cut -f1)"; done
