#!/usr/bin/env bash
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"
source_commit=$(git rev-parse --verify --end-of-options "${1:?Specify a Beta commit or branch}^{commit}")
target=meter_ocr_beta
staging=$(mktemp -d)
trap 'rm -rf -- "$staging"' EXIT

git archive "$source_commit" -- rf1_ocr_test | tar -x -C "$staging"
package="$staging/rf1_ocr_test"
rm -rf -- "$package/tests" "$package/README.md" "$package/README.en.md" "$package/DOCS.md"
sed \
    -e 's/^name: .*/name: Meter OCR Beta/' \
    -e 's/^slug: .*/slug: meter_ocr_beta/' \
    -e 's/^boot: .*/boot: manual/' \
    -e 's/^description: .*/description: "Test builds of Meter OCR with separate sensors and settings."/' \
    -e '/^stage: /d' \
    "$package/config.yaml" > "$staging/config.yaml"
printf '\nstage: experimental\n' >> "$staging/config.yaml"
mv "$staging/config.yaml" "$package/config.yaml"
printf '\nENV METER_OCR_CHANNEL=beta\n' >> "$package/Dockerfile"
printf '%s\n' "$source_commit" > "$package/SOURCE"

if [[ "${2:-}" == "--check" ]]; then
    diff -qr --exclude=DOCS.md -- "$package" "$target"
else
    mkdir -p "$target"
    cp -a "$package/." "$target/"
fi
