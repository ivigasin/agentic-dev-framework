#!/usr/bin/env bash
# SessionStart hook: inject the bootstrap + routers into every session.
# Keeps injected context under ~2K tokens; everything else is lazy-loaded.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
echo "=== FRAMEWORK BOOTSTRAP ==="
cat "$ROOT/CLAUDE.md"
echo ""
echo "=== SKILLS INDEX ==="
cat "$ROOT/skills/INDEX.md"
echo ""
echo "=== WIKI INDEX ==="
cat "$ROOT/wiki/INDEX.md"
