#!/usr/bin/env bash
# Backtest corpus: merged optimization PRs opened by the Codeflash bot outside Codeflash's own org.
# Writes artifacts/corpus/codeflash_prs.json (repo, number, title, url, merged date).
set -euo pipefail
mkdir -p artifacts/corpus
gh search prs --author "app/codeflash-ai" --merged --limit 1000 \
  --json repository,number,title,url,closedAt \
  --jq '[.[] | select(.repository.nameWithOwner | startswith("codeflash-ai/") | not)
         | {repo: .repository.nameWithOwner, number, title, url, merged: .closedAt}]' \
  > artifacts/corpus/codeflash_prs.json
python3 - <<'EOF'
import collections, json
prs = json.load(open("artifacts/corpus/codeflash_prs.json"))
by = collections.Counter(p["repo"] for p in prs)
print(f"{len(prs)} merged PRs across {len(by)} repos (excluding codeflash-ai/*)")
for repo, n in by.most_common(10):
    print(f"  {n:3d}  {repo}")
EOF
