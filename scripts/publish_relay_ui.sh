#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$1" && pwd)
build=$(jq -er '.build | select(test("^[0-9a-f]{64}$"))' "$root/relay-ui.json")
asset="ui-$build.zip"
if ! gh release view relay-ui >/dev/null 2>&1; then
  gh release create relay-ui --prerelease --latest=false --target "$GITHUB_SHA" --title 'Mower 中转前端' --notes '供中转网关按实例构建标识下载。' || gh release view relay-ui >/dev/null
fi
has_asset() {
  gh release view relay-ui --json assets --jq '.assets[].name' | grep -Fx "$asset" >/dev/null
}
if ! has_asset; then
  stage=$(mktemp -d)
  trap 'rm -rf -- "$stage"' EXIT
  (cd "$root" && zip -qr "$stage/$asset" .)
  gh release upload relay-ui "$stage/$asset" || has_asset
fi
