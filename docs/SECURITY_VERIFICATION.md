# Security & Release Verification

This document explains how to verify BiRRe releases using cryptographic signatures.

## Release Signing

All BiRRe releases starting from v4.0.0 are signed using [Sigstore](https://www.sigstore.dev/),
providing cryptographic verification of release artifacts.

### What Gets Signed

Each release includes signed artifacts:

- Source distribution (`.tar.gz`)
- Wheel distribution (`.whl`)
- Signature bundles (`.sigstore.json`)

### Why Sign Releases

Release signing provides:

1. **Authenticity** - Verify releases come from BiRRe maintainers
2. **Integrity** - Detect tampering or corruption
3. **Non-repudiation** - Signed releases cannot be denied
4. **Supply chain security** - Protect against compromised distribution channels

## Verifying Releases

### Prerequisites

Install the Sigstore CLI:

```bash
# Using pip
pip install sigstore

# Using pipx (recommended)
pipx install sigstore
```

### Verification Steps

1. **Download release artifacts** from [GitHub Releases](https://github.com/boecht/birre/releases):

    - `birre-X.Y.Z.tar.gz` (source distribution)
    - `birre-X.Y.Z-py3-none-any.whl` (wheel)
    - `birre-X.Y.Z.tar.gz.sigstore.json` (signature bundle)

2. **Verify the signature**:

```bash
# Verify source distribution
sigstore verify github \
  --bundle birre-X.Y.Z.tar.gz.sigstore.json \
  --cert-identity https://github.com/boecht/birre/.github/workflows/release.yml@refs/tags/vX.Y.Z \
  --repo boecht/birre \
  birre-X.Y.Z.tar.gz

# Verify wheel distribution
sigstore verify github \
  --bundle birre-X.Y.Z-py3-none-any.whl.sigstore.json \
  --cert-identity https://github.com/boecht/birre/.github/workflows/release.yml@refs/tags/vX.Y.Z \
  --repo boecht/birre \
  birre-X.Y.Z-py3-none-any.whl
```

**Expected output**:

```text
OK: birre-X.Y.Z.tar.gz
Trusted
```

### Understanding Verification

**Certificate Identity**: The release workflow's GitHub Actions identity
**Repository**: The source repository (prevents impersonation)
**Transparency Log**: Public ledger ensuring signatures cannot be backdated

## PyPI Package Verification

PyPI packages include attestations starting from v4.0.0.

### Verify PyPI Download

```bash
# Download and verify in one step
pip install birre --verify-with-sigstore

# Manual verification
pip download birre --no-deps
sigstore verify github \
  --bundle birre-X.Y.Z-py3-none-any.whl.sigstore.json \
  --cert-identity https://github.com/boecht/birre/.github/workflows/release.yml@refs/tags/vX.Y.Z \
  --repo boecht/birre \
  birre-X.Y.Z-py3-none-any.whl
```

## Security Best Practices

### For Users

1. **Always verify signatures** before installing from GitHub releases
2. **Use PyPI trusted publishers** when installing via pip
3. **Check package hashes** match published values
4. **Report suspicious artifacts** via [GitHub Security Advisories](https://github.com/boecht/birre/security/advisories)

### For Developers

1. **Never manually sign releases** - automated signing only
2. **Verify signatures** in PR validation workflow
3. **Monitor transparency logs** for unexpected signatures
4. **Rotate signing keys** according to policy (Sigstore handles this automatically)

## Troubleshooting

### Verification Fails

**Symptom**: `sigstore verify` returns error

**Common Causes**:

1. **Wrong certificate identity** - Ensure you use the exact workflow path with tag
2. **Corrupted download** - Re-download artifact and try again
3. **Mismatched bundle** - Ensure `.sigstore.json` matches artifact filename
4. **Network issues** - Verification requires internet for transparency log

### Missing Signature Bundle

**Symptom**: No `.sigstore.json` file in release

**Solution**: Older releases (< v4.0.0) were not signed. Only verify v4.0.0+.

### Certificate Expired

**Symptom**: Certificate validation error

**Solution**: Sigstore uses short-lived certificates. This is expected and verified
against the transparency log timestamp.

## Advanced Verification

### Inspect Signature Bundle

```bash
# View bundle contents
cat birre-X.Y.Z.tar.gz.sigstore.json | jq

# Extract certificate
jq -r '.verificationMaterial.x509CertificateChain.certificates[0].rawBytes' \
  birre-X.Y.Z.tar.gz.sigstore.json | base64 -d | openssl x509 -text -noout
```

### Verify Against Specific Commit

```bash
# Find commit SHA for release tag
git rev-parse vX.Y.Z

# Verify bundle references correct commit
jq -r '.verificationMaterial.x509CertificateChain.certificates[0]' \
  birre-X.Y.Z.tar.gz.sigstore.json | base64 -d | openssl x509 -text | grep -A1 "Subject Alternative Name"
```

### Check Transparency Log Entry

```bash
# Verify entry exists in Rekor transparency log
rekor-cli search --artifact birre-X.Y.Z.tar.gz

# View entry details
rekor-cli get --uuid <UUID_FROM_SEARCH>
```

## Resources

- [Sigstore Documentation](https://docs.sigstore.dev/)
- [Python Signing Guide](https://docs.sigstore.dev/signing/quickstart/)
- [Verification Guide](https://docs.sigstore.dev/verifying/verify/)
- [Rekor Transparency Log](https://rekor.sigstore.dev/)
- [Security Policy](../SECURITY.md)

### Security Issues

See [SECURITY.md](../SECURITY.md) for responsible disclosure.
