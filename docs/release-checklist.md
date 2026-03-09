# LACP Release Checklist

Use this checklist before tagging any release.

## 1) Validate locally

```bash
cd /path/to/lacp
bin/lacp-test --isolated
bin/lacp release-prepare --quick --skip-cache-gate --skip-skill-audit-gate --json | jq
bin/lacp release-verify --tag vX.Y.Z --quick --skip-cache-gate --skip-skill-audit-gate --json | jq
```

Pass criteria:
- `lacp-test --isolated` exits `0`
- `release-prepare.ok == true`
- `release-verify.ok == true`

## 2) Verify docs + changelog

- Update `CHANGELOG.md`:
  - move release items from `Unreleased` into versioned block
  - add compare/release link at bottom
- Confirm command docs:
  - `README.md`
  - `docs/runbook.md`

## 3) Commit release prep

```bash
cd /path/to/lacp
git add .
git commit -m "chore(release): prepare vX.Y.Z"
git push origin main
```

## 4) Tag + push

```bash
cd /path/to/lacp
git tag -a vX.Y.Z -m "vX.Y.Z"
git push origin vX.Y.Z
```

## 5) Publish assets from local machine (no Actions)

```bash
cd /path/to/lacp
bin/lacp release-publish \
  --tag vX.Y.Z \
  --quick \
  --skip-cache-gate \
  --skip-skill-audit-gate \
  --json | jq
```

This command:
- runs `release-prepare` (unless `--skip-prepare` is set)
- builds `lacp-X.Y.Z.tar.gz` from the tagged commit via `git archive`
- writes `SHA256SUMS`
- creates or updates GitHub Release assets via `gh` (unless `--skip-gh`)

## 6) Verify GitHub release assets (optional)

```bash
gh release view vX.Y.Z -R 0xNyk/lacp
gh release download vX.Y.Z -R 0xNyk/lacp -D /tmp/lacp-release-check
cd /tmp/lacp-release-check
shasum -a 256 -c SHA256SUMS
```

## 7) Homebrew tap update

```bash
# In lacp repo
cd /path/to/lacp
TAR_URL="https://github.com/0xNyk/lacp/releases/download/vX.Y.Z/lacp-X.Y.Z.tar.gz"
SHA="$(curl -fsSL "$TAR_URL" | shasum -a 256 | awk '{print $1}')"
echo "$SHA"
```

Update `homebrew-lacp/Formula/lacp.rb`:
- set `url` to release tarball URL
- set `sha256` to computed digest

Then:

```bash
cd /path/to/homebrew-lacp
git add Formula/lacp.rb README.md
git commit -m "chore(release): lacp vX.Y.Z"
git push origin main
```

## 8) Clean install smoke

```bash
brew uninstall lacp || true
brew tap 0xNyk/lacp
brew install lacp
lacp --help
lacp doctor --json | jq '.ok,.summary'
```
