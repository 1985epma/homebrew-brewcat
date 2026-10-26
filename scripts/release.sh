#!/usr/bin/env bash
# Publish a new brewcat version end to end: bump, commit, tag, GitHub release (.dmg), formula and cask sha256.
#
#   scripts/release.sh 0.1.3                 # dry run: checks everything, prints the plan, changes nothing
#   scripts/release.sh 0.1.3 --yes           # really publish
#   scripts/release.sh 0.1.3 --yes --notes "What changed" [--local-upgrade]
#
# Rules it enforces: the version must be newer, the tag must not exist yet (tags are never moved),
# the working tree must be clean and in sync with origin/main, and every sha256 is verified against
# what GitHub really serves (curl -f, so a 404 page can never be hashed by mistake).
set -Eeuo pipefail
cd "$(dirname "$0")/.."

REPO="1985epma/homebrew-brewcat"
die() { echo "release: $*" >&2; exit 1; }
usage() { sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }

VERSION="" YES=0 NOTES="" LOCAL=0
while (( $# )); do
  case $1 in
    --yes) YES=1 ;;
    --notes) NOTES=${2:?--notes needs a text}; shift ;;
    --local-upgrade) LOCAL=1 ;;
    -h|--help) usage ;;
    -*) die "unknown option: $1 (try --help)" ;;
    *) [[ -z $VERSION ]] || die "only one version allowed"; VERSION=$1 ;;
  esac
  shift
done
[[ -n $VERSION ]] || usage
[[ $VERSION =~ ^[0-9]+(\.[0-9]+){2,3}$ ]] || die "version must look like 0.1.3 or 0.1.2.7"
TAG="v$VERSION"

CURRENT=$(sed -n 's/^VERSION = "\(.*\)"$/\1/p' help_text.py)
[[ -n $CURRENT ]] || die "cannot read VERSION from help_text.py"
[[ $CURRENT != "$VERSION" && $(printf '%s\n%s\n' "$CURRENT" "$VERSION" | sort -V | tail -1) == "$VERSION" ]] \
  || die "version $VERSION is not newer than the current $CURRENT"

# ── preconditions (always checked, also in dry run) ──
command -v gh >/dev/null || die "gh (GitHub CLI) is required"
gh auth status >/dev/null 2>&1 || die "gh is not logged in (gh auth login)"
[[ $(git rev-parse --abbrev-ref HEAD) == main ]] || die "run this from the main branch"
[[ -z $(git status --porcelain) ]] || die "uncommitted changes: commit them first (a release commit only bumps the version)"
git fetch -q origin main --tags
[[ $(git rev-parse HEAD) == "$(git rev-parse origin/main)" ]] || die "main is not in sync with origin/main (pull or push first)"
if git rev-parse -q --verify "refs/tags/$TAG" >/dev/null || git ls-remote --exit-code --tags origin "$TAG" >/dev/null 2>&1; then
  die "tag $TAG already exists. Tags are never moved: pick a new version"
fi
python3 -m compileall -q ./*.py >/dev/null || die "Python files do not compile"

cat <<PLAN
Release plan: $CURRENT -> $VERSION  (tag $TAG)
  1. set VERSION in help_text.py, the formula url and the cask version
  2. verify 'brewcat --version', commit "Release $VERSION", push main, create and push tag $TAG
  3. sha256 of the GitHub tarball -> Formula/brewcat.rb
  4. build dist/brewcat-$VERSION.dmg and create the GitHub release with it
  5. sha256 of the published .dmg -> Casks/brewcat.rb, commit and push
  6. verify every sha256 again from what GitHub serves$( ((LOCAL)) && echo "; brew upgrade + brew test here")
PLAN
if (( ! YES )); then echo; echo "Dry run only. Re-run with --yes to publish."; exit 0; fi

step() { echo; echo "==> $*"; }
trap 'echo; echo "release: FAILED at the step above. The tag may already be public: do NOT move it; fix forward with a new version." >&2' ERR

fetch_sha() { # sha256 of a URL, retrying while GitHub finishes publishing it; fails on HTTP errors
  local url=$1 sha
  for _ in 1 2 3 4 5 6; do
    if sha=$(curl -fsSL "$url" | shasum -a 256 | cut -d' ' -f1) && [[ -n $sha ]]; then echo "$sha"; return 0; fi
    sleep 3
  done
  return 1
}

step "1/6 bump version"
perl -pi -e "s/^VERSION = \".*\"/VERSION = \"$VERSION\"/" help_text.py
perl -pi -e "s{/archive/refs/tags/v[0-9.]+\.tar\.gz}{/archive/refs/tags/$TAG.tar.gz}" Formula/brewcat.rb
perl -pi -e "s/^  version \".*\"/  version \"$VERSION\"/" Casks/brewcat.rb

step "2/6 verify, commit, push, tag"
[[ $(python3 app.py --version | head -1) == "brewcat $VERSION" ]] || die "app reports a different version"
git add help_text.py Formula/brewcat.rb Casks/brewcat.rb
git commit -q -m "Release $VERSION"
git push -q origin main
git tag "$TAG"
git push -q origin "$TAG"

step "3/6 formula sha256"
TAR_URL="https://github.com/$REPO/archive/refs/tags/$TAG.tar.gz"
TAR_SHA=$(fetch_sha "$TAR_URL") || die "could not download $TAR_URL"
perl -pi -e "s/sha256 \"[0-9a-f]+\"/sha256 \"$TAR_SHA\"/" Formula/brewcat.rb
echo "$TAR_SHA"

step "4/6 build .dmg and create the GitHub release"
./scripts/build-dmg.sh "$VERSION" 2>&1 | grep -v deprecated || true
[[ -f dist/brewcat-$VERSION.dmg ]] || die "dmg was not built"
if [[ -n $NOTES ]]; then
  gh release create "$TAG" "dist/brewcat-$VERSION.dmg" --title "$TAG" --notes "$NOTES"
else
  gh release create "$TAG" "dist/brewcat-$VERSION.dmg" --title "$TAG" --generate-notes
fi

step "5/6 cask sha256"
DMG_URL="https://github.com/$REPO/releases/download/$TAG/brewcat-$VERSION.dmg"
DMG_SHA=$(fetch_sha "$DMG_URL") || die "could not download $DMG_URL"
[[ $DMG_SHA == "$(shasum -a 256 "dist/brewcat-$VERSION.dmg" | cut -d' ' -f1)" ]] || die "published .dmg differs from the local one"
perl -pi -e "s/sha256 \"[0-9a-f]+\"/sha256 \"$DMG_SHA\"/" Casks/brewcat.rb
git add Formula/brewcat.rb Casks/brewcat.rb
git commit -q -m "Set brewcat $VERSION sha256 (formula and cask)"
git push -q origin main

step "6/6 verify what GitHub serves"
[[ $(fetch_sha "$TAR_URL") == "$(sed -n 's/^ *sha256 "\(.*\)"/\1/p' Formula/brewcat.rb)" ]] || die "formula sha256 mismatch"
[[ $(fetch_sha "$DMG_URL") == "$(sed -n 's/^ *sha256 "\(.*\)"/\1/p' Casks/brewcat.rb)" ]] || die "cask sha256 mismatch"
ruby -c Formula/brewcat.rb >/dev/null && ruby -c Casks/brewcat.rb >/dev/null
if (( LOCAL )); then
  brew update >/dev/null 2>&1 || true
  brew upgrade 1985epma/brewcat/brewcat
  brew test 1985epma/brewcat/brewcat
  brewcat --version | head -1
fi
trap - ERR
echo; echo "Released $TAG: https://github.com/$REPO/releases/tag/$TAG"
echo "Users update with: brew update && brew upgrade brewcat   (cask: brew upgrade --cask brewcat)"
