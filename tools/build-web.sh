#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Build the WASM linter and place it next to the web app.
#
# Prerequisite (one-off):  rustup target add wasm32-unknown-unknown
# Homebrew's rust does not ship that target and has no rustup, so this needs a
# rustup-managed toolchain.
set -euo pipefail
cd "$(dirname "$0")/.."

if ! rustc --print target-list 2>/dev/null | grep -qx wasm32-unknown-unknown; then
  echo "error: wasm32-unknown-unknown is not available to this toolchain." >&2
  echo "       Install rustup, then: rustup target add wasm32-unknown-unknown" >&2
  exit 1
fi

cargo build -p sumo-lint-wasm --release --target wasm32-unknown-unknown
cp target/wasm32-unknown-unknown/release/sumo_lint_wasm.wasm web/

echo "built web/sumo_lint_wasm.wasm ($(du -h web/sumo_lint_wasm.wasm | cut -f1))"
echo "serve locally with:  python3 -m http.server -d web 8080"
