#!/bin/sh
# Publish a directory (web/ by default) as the gh-pages branch of a remote
# (origin by default), replacing what was there: one commit, force-pushed.
set -eu
site=${1:-web}
remote=${2:-origin}
url=$(git remote get-url "$remote")
source=$(git rev-parse --short HEAD)
name=$(git config user.name)
email=$(git config user.email)
[ -f "$site/index.html" ] || { echo "no $site/index.html: run make build-web" >&2; exit 1; }
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cp -R "$site"/. "$work"/
cd "$work"
git init -q -b gh-pages
git add -A
git -c user.name="$name" -c user.email="$email" commit -q -m "Publish the web build of $source"
git push -q --force "$url" gh-pages
echo "published $site to $remote gh-pages ($source)"
