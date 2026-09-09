#!/usr/bin/env bash
# Assemble the Lambda deployment payload at infra/build/lambda/.
#
# Terraform's archive_file zips this directory (see api.tf) rather than the
# script producing the zip, so the deployed artifact hash tracks content and
# `terraform apply` is a no-op when nothing changed.
#
# The output must be BYTE-IDENTICAL for the same inputs on any machine.
# Otherwise a laptop and a CI runner disagree on source_code_hash, Terraform
# reports a Lambda update on every plan, and no plan is ever clean. Every
# choice below that looks fussy is protecting that property.
#
# Run this before `terraform plan`/`apply` whenever backend/ changes.
set -euo pipefail

INFRA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "$INFRA_DIR/.." && pwd)"
BACKEND_DIR="$REPO_ROOT/backend"
BUILD_DIR="$INFRA_DIR/build/lambda"

PYTHON="${PYTHON:-python3}"

# Must match aws_lambda_function.api in api.tf.
PYTHON_VERSION="3.13"
PLATFORM="manylinux2014_aarch64"  # arm64 / Graviton

echo "==> Cleaning $BUILD_DIR"
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

# Dependencies are read from pyproject.toml rather than duplicated here, so
# there is still one source of truth -- but the backend itself is NOT pip
# installed. Installing it would mean building its wheel, which drags in
# whatever build backend version pip resolves that day plus a direct_url.json
# recording the mktemp path it was built in, both of which differ per machine.
# Copying the source in sidesteps all of it.
echo "==> Reading dependencies from pyproject.toml"
# Read into an array with a while-loop rather than mapfile: macOS ships
# bash 3.2, which predates mapfile, and this script has to run identically
# there and on the Ubuntu runner.
DEPS=()
while IFS= read -r dep; do
    [ -n "$dep" ] && DEPS+=("$dep")
done < <("$PYTHON" - "$BACKEND_DIR/pyproject.toml" <<'PYEOF'
import sys, tomllib
with open(sys.argv[1], "rb") as fh:
    print("\n".join(tomllib.load(fh)["project"]["dependencies"]))
PYEOF
)
printf '    %s\n' "${DEPS[@]}"

echo "==> Vendoring dependencies for python$PYTHON_VERSION/$PLATFORM"
# --platform/--python-version pin the wheels to the Lambda runtime rather
# than the machine running this script. Every current dependency is pure
# Python, but MarkupSafe (via Jinja2) ships an optional compiled speedup, and
# a macOS/arm .so in the bundle is exactly the kind of thing that fails only
# once it is deployed.
"$PYTHON" -m pip install \
    --target "$BUILD_DIR" \
    --platform "$PLATFORM" \
    --implementation cp \
    --python-version "$PYTHON_VERSION" \
    --only-binary=:all: \
    --upgrade \
    --quiet \
    "${DEPS[@]}"

echo "==> Adding application source"
cp -R "$BACKEND_DIR/app" "$BUILD_DIR/app"
# The API calls the canonical, provider-agnostic Investigator/Skeptic module
# from data_pipeline. Package only that pure-Python namespace rather than
# copying the source-fetching and offline enrichment tools into Lambda.
mkdir -p "$BUILD_DIR/data_pipeline"
cp "$REPO_ROOT/data_pipeline/__init__.py" "$BUILD_DIR/data_pipeline/__init__.py"
cp -R "$REPO_ROOT/data_pipeline/analysis" "$BUILD_DIR/data_pipeline/analysis"
# wsgi.py is the local dev server and has no place in the bundle.
cp "$BACKEND_DIR/lambda_handler.py" "$BUILD_DIR/lambda_handler.py"

# Console-script wrappers (bin/flask, bin/dotenv) are generated with a shebang
# pointing at the interpreter that ran pip -- /opt/homebrew/... on a Mac,
# /opt/hostedtoolcache/... on a runner. Lambda invokes the handler directly and
# never uses them, and they are the single biggest source of cross-machine
# hash drift.
rm -rf "$BUILD_DIR/bin"

# Each such script is also listed in its package's RECORD, with the script's
# hash and size -- and the shebang path length differs per machine, so those
# lines differ too. RECORD is pip uninstall bookkeeping and is never read at
# runtime; the rest of it stays intact.
find "$BUILD_DIR" -name 'RECORD' -exec sed -i.bak '/^\.\.\/\.\.\/bin\//d' {} +
find "$BUILD_DIR" -name 'RECORD.bak' -delete

# .dist-info is deliberately kept -- Flask reads its own version through
# importlib.metadata, which needs it.
find "$BUILD_DIR" -type d -name '__pycache__' -prune -exec rm -rf {} +

echo "==> Built $BUILD_DIR ($(du -sh "$BUILD_DIR" | cut -f1))"
echo "    Next: cd infra && terraform apply"
