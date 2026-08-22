#!/usr/bin/env bash
# Fetch all James Joyce letter XML files from the University of Antwerp
# correspondence database into ./xml
#
# The list of letter filenames is read from letter_ids.txt (one filename
# per line, e.g. L_71294.xml), generated from the correspondence table at
# https://joyceletters.uantwerpen.be/exist/apps/jjletters/correspondence
set -euo pipefail

BASE_URL="https://joyceletters.uantwerpen.be/exist/apps/jjletters/api/document"
IDS_FILE="$(dirname "$0")/letter_ids.txt"
OUT_DIR="$(dirname "$0")/xml"

mkdir -p "$OUT_DIR"

total=$(wc -l < "$IDS_FILE")
count=0
failed=()

while IFS= read -r name; do
    [ -z "$name" ] && continue
    count=$((count + 1))
    dest="$OUT_DIR/$name"
    if [ -f "$dest" ] && [ -s "$dest" ]; then
        echo "[$count/$total] skip (exists): $name"
        continue
    fi
    echo "[$count/$total] fetching: $name"
    if ! curl -s -f "$BASE_URL/$name" -o "$dest"; then
        echo "  FAILED: $name"
        failed+=("$name")
        rm -f "$dest"
    fi
    sleep 0.3
done < "$IDS_FILE"

echo "Done. Fetched into $OUT_DIR"
if [ ${#failed[@]} -gt 0 ]; then
    echo "Failed (${#failed[@]}):"
    printf '  %s\n' "${failed[@]}"
fi
