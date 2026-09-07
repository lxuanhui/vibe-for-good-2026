#!/usr/bin/env bash
# Assemble the Lambda deployment payload at infra/build/lambda/.
#
# Terraform's archive_file zips this directory (see api.tf) rather than the
# script producing the zip, so the deployed artifact hash tracks content and
# `terraform apply` is a no-op when nothing changed.
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

WHEEL_DIR="$(mktemp -d)"
trap 'rm -rf "$WHEEL_DIR"' EXIT

# Two steps rather than one `pip install <backend dir>`: the vendoring step
# below passes --only-binary=:all: (needed alongside --platform), which
# forbids building anything from source -- including the backend project
# itself. Building its wheel first sidesteps that; the wheel is
# py3-none-any, so it stays valid for the Lambda target.
echo "==> Building backend wheel"
"$PYTHON" -m pip wheel --no-deps --wheel-dir "$WHEEL_DIR" --quiet "$BACKEND_DIR"

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
    "$WHEEL_DIR"/*.whl

echo "==> Adding Lambda entrypoint"
# The `app` package itself arrives via the wheel above. wsgi.py is the local
# dev server and has no place in the bundle, so only the handler is copied.
cp "$BACKEND_DIR/lambda_handler.py" "$BUILD_DIR/lambda_handler.py"

# .dist-info is deliberately kept -- Flask reads its own version through
# importlib.metadata, which needs it.
find "$BUILD_DIR" -type d -name '__pycache__' -prune -exec rm -rf {} +

echo "==> Built $BUILD_DIR ($(du -sh "$BUILD_DIR" | cut -f1))"
echo "    Next: cd infra && terraform apply"
