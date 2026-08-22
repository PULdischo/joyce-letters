#!/usr/bin/env bash
# Fetch all canonical person biography records from the JJ Letters "List of
# People Mentioned" register (202 entries) into ./xml/people
set -euo pipefail
BASE_URL="https://joyceletters.uantwerpen.be/exist/apps/jjletters/api/document"
IDS_FILE="$(dirname "$0")/people_keys.txt"
OUT_DIR="$(dirname "$0")/xml/people"
mkdir -p "$OUT_DIR"
total=$(wc -l < "$IDS_FILE")
count=0
failed=()
while IFS= read -r key; do
    [ -z "$key" ] && continue
    count=$((count + 1))
    dest="$OUT_DIR/$key.xml"
    if [ -f "$dest" ] && [ -s "$dest" ]; then
        echo "[$count/$total] skip (exists): $key"
        continue
    fi
    echo "[$count/$total] fetching: $key"
    if ! curl -s -f "$BASE_URL/$key.xml" -o "$dest"; then
        echo "  FAILED: $key"
        failed+=("$key")
        rm -f "$dest"
    fi
    sleep 0.3
done < "$IDS_FILE"
echo "Done. Fetched into $OUT_DIR"
if [ ${#failed[@]} -gt 0 ]; then
    echo "Failed (${#failed[@]}):"
    printf '  %s\n' "${failed[@]}"
fi
