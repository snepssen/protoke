#!/bin/bash
# macOS launcher: the same as start.sh, double-clickable from Finder.
cd "$(dirname "$0")" || exit 1
exec ./start.sh "$@"
