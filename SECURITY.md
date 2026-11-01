# Security policy

brewcat installs software on your machine, so security reports are taken seriously.

## Reporting a vulnerability

Please **do not open a public issue** for a security problem. Use GitHub's private reporting instead:

1. Go to the [Security tab](https://github.com/1985epma/homebrew-brewcat/security) of this repository.
2. Click **Report a vulnerability** and describe what you found, how to reproduce it and what you expect the impact to be.

brewcat is maintained by one person, so replies are best effort. You will get an acknowledgement as soon as the
report is read; a fix is released as a new version (tags are never moved or rewritten).

## What is in scope

- the app and the command line (`app.py`, `cli.py`, `gui.py` and the other modules in this repository);
- `install.sh`, `scripts/` and the release artifacts (the `.dmg`, the formula and the cask);
- the logic that installs skills and MCP servers (repository parsing, symlink and script checks, config edits);
- anything that could make brewcat run a command you did not confirm, or write outside the folders it is meant to use.

## What is out of scope

- Vulnerabilities in the packages the catalog lists (Homebrew formulae and casks). Report those to the package's
  own project or to Homebrew.
- Skills and MCP servers you choose to install from a repository you do not trust. brewcat shows their source and
  warns about scripts, but running third-party code is your decision.
- The macOS app is ad-hoc signed and **not notarized** by Apple (see the README). That is a known, documented
  limitation, not a vulnerability.

## Supported versions

Only the latest release receives fixes. Update with `brew update && brew upgrade brewcat`
(cask: `brew upgrade --cask brewcat`).
