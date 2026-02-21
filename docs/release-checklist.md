# LACP Release Checklist

Use this checklist before tagging any release.

## 1) Validate locally

```bash
cd ~/control/frameworks/lacp
bin/lacp-test --isolated
bin/lacp release-prepare --quick --skip-cache-gate --skip-skill-audit-gate --json | jq
```

Pass criteria:
- `lacp-test --isolated` exits `0`
- `release-prepare.ok == true`

## 2) Verify docs + changelog

- Update `CHANGELOG.md`:
  - move release items from `Unreleased` into versioned block
  - add compare/release link at bottom
- Confirm command docs:
  - `README.md`
  - `docs/runbook.md`

## 3) Commit release prep

```bash
cd ~/control/frameworks/lacp
git add .
git commit -m "chore(release): prepare vX.Y.Z"
git push origin main
```

## 4) Tag + push

```bash
cd ~/control/frameworks/lacp
git tag -a vX.Y.Z -m "vX.Y.Z"
git push origin vX.Y.Z
```

This triggers `.github/workflows/release.yml` to publish:
- `lacp-X.Y.Z.tar.gz`
- `SHA256SUMS`

## 5) Verify GitHub release

```bash
gh release view vX.Y.Z -R 0xNyk/lacp
gh release download vX.Y.Z -R 0xNyk/lacp -D /tmp/lacp-release-check
cd /tmp/lacp-release-check
shasum -a 256 -c SHA256SUMS
```

## 6) Homebrew tap update

```bash
# In lacp repo
cd ~/control/frameworks/lacp
TAR_URL="https://github.com/0xNyk/lacp/releases/download/vX.Y.Z/lacp-X.Y.Z.tar.gz"
SHA="$(curl -fsSL "$TAR_URL" | shasum -a 256 | awk '{print $1}')"
echo "$SHA"
```

Update `homebrew-lacp/Formula/lacp.rb`:
- set `url` to release tarball URL
- set `sha256` to computed digest

Then:

```bash
cd ~/control/frameworks/homebrew-lacp
git add Formula/lacp.rb README.md
git commit -m "chore(release): lacp vX.Y.Z"
git push origin main
```

## 7) Clean install smoke

```bash
brew uninstall lacp || true
brew tap 0xNyk/lacp
brew install lacp
lacp --help
lacp doctor --json | jq '.ok,.summary'
```
