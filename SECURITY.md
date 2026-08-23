# Security and privacy policy

TraderResearch is designed as a public repository. Treat every tracked file and every Git
commit as permanently public.

## Never commit

- credentials, API keys, secrets, passwords, session cookies, or authentication tokens;
- Reddit, GitHub, operating-system, or brokerage usernames;
- brokerage account identifiers, balances, statements, or tax information;
- real names, personal email addresses, phone numbers, home addresses, hostnames, private IPs,
  or personal filesystem paths;
- `.env` files, runtime databases, logs, private datasets, credentials, or key material; or
- raw provider data unless its collection, retention, and publication are explicitly permitted.

Use a secure environment or secret manager. `.env.example` is a schema made only of generic
placeholders; it is not a credential store. Runtime data belongs in the OS application-data
directory or another external, access-controlled location.

Raw social-media usernames must be pseudonymized at the collection boundary with a keyed
one-way function before they reach application models, storage, logs, exceptions, or CLI
output. Do not use an unkeyed username hash: predictable identifiers can be enumerated.
TraderResearch's structured logger redacts identifier fields, common credential formats,
private paths, private network addresses, account-like identifiers, and nested sensitive keys.

## Before every commit

1. Review staged filenames and the complete staged diff.
2. Confirm `.gitignore` still excludes `.env`, databases, logs, keys, and private directories.
3. Run formatting, linting, tests, and pre-commit hooks.
4. Run gitleaks over the repository and staged content.
5. Search the staged diff for credentials, account IDs, personal data, private network values,
   machine-specific paths, and unexpected high-entropy strings.
6. Stop and remove anything uncertain before committing.

Suggested local setup:

```bash
python -m pip install -e '.[dev]'
pre-commit install
pre-commit run --all-files
gitleaks git --redact
```

CI repeats tests and secret scanning. Automated scans supplement careful review; they do not
replace it.

## If sensitive data enters history

Deleting it in a later commit is not sufficient because Git preserves earlier objects. Stop
publishing, rotate or revoke the exposed credential, identify affected clones and artifacts,
rewrite history with an appropriate tool, force-update authorized remotes, and verify the
entire rewritten history. Coordinate disclosure privately; do not paste the secret into an
issue or pull request.

## Reporting a vulnerability

Do not include secrets, account data, personal data, or exploit payloads in a public issue.
Use the repository host's private security-advisory feature when one is available. A public
security contact is intentionally not embedded in this initial repository.
