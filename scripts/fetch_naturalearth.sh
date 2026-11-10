#!/usr/bin/env bash
# Fetch Natural Earth (public domain) 50m/10m land polygons into data/external/naturalearth/.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
out="$root/data/external/naturalearth"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
git clone --depth 1 --filter=blob:none --sparse \
    https://github.com/nvkelso/natural-earth-vector.git "$tmp/ne"
git -C "$tmp/ne" sparse-checkout set 50m_physical 10m_physical
mkdir -p "$out"
for res in 50m 10m; do
    cp "$tmp"/ne/${res}_physical/ne_${res}_land.* "$out"/
done
echo "Natural Earth land written to $out"
