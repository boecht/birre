# Security Policy

## Supported Versions

- Only the most recent **stable release** (currently v4.0.0) receives security updates.
- Older tags are considered end-of-life.
- Pre-release builds (alpha, beta, RC) are **not** covered; use them at your own risk.

## Reporting a Vulnerability

Report privately via [GitHub Security Advisories](https://github.com/boecht/birre/security/advisories).
Please include reproduction steps, expected vs. actual behaviour, logs, and any mitigating context.

We aim to acknowledge new reports within **five business days** and will keep you informed throughout
triage and remediation.

## Release Verification & Supply Chain

BiRRe releases ship with:

- Sigstore signing (Fulcio + Rekor) for artifacts and GitHub releases.
- Software Bills of Materials (SBOMs) and dependency review logs.
- Trusted publisher deployment to PyPI (artifact hashes match GitHub releases).

Follow [docs/SECURITY_VERIFICATION.md](docs/SECURITY_VERIFICATION.md) to verify downloaded artifacts and PyPI
installations. If you detect tampering, contact the maintainers via Security Advisories immediately.
