---
format: decision
title: Hybrid encryption for local credentials
status: implemented
category: architecture
date: 2026-11-16
---

# Hybrid encryption for local credentials

## Problem

Mower's existing configuration files store credentials as plaintext. This change
introduces encrypted local credential storage for the first time. It must use
X25519 and ML-KEM-768 hybrid encapsulation on every supported platform, migrate
the actual plaintext sources safely, and preserve existing settings operations.
The [configuration backup subsystem description](../../../../docs/subsystems/config-backup.md#configuration-credential-storage)
owns storage, migration and backup behavior. There is no previously released
encrypted credential format to retain.

## Decision

[`credential_store.py`](../../../../arknights_mower/utils/credential_store.py)
uses `cryptography==50.0.2` HPKE with X-Wing (`MLKEM768_X25519`),
`HKDF_SHA256` and `AES_256_GCM`. One fixed recipient private key is initialized
for the selected provider and reused for ordinary credential saves. HPKE still
produces a fresh encapsulation and ciphertext for each encryption.

The private key is protected directly by Windows DPAPI, macOS Keychain or Linux
Secret Service. Deployments without the desktop service use a private file;
an explicitly selected existing private-key file is also supported. Reads can
use that explicitly supplied original key across providers while authenticating
the original header and matching its public-key identifier; this is not an
automatic fallback. The
default private key is shared across the same system user's instances with the
same storage settings; explicitly selected different private keys can isolate
deployments. The credential envelope contains the provider and public-key identifier, not a copy
of the private key. The authenticated HPKE context binds that header to the
ciphertext. The subsystem description owns the exact format and platform paths.

Keeping a fixed private key avoids another master-key layer and does not make
ordinary edits change the recipient identity. Initialization records and key
identifiers make a missing or mismatched key an error instead of an occasion to
create a replacement. Atomic writes and readback validation preserve the prior
bytes on failure. Plaintext sources are removed only after their encrypted
destination is written and verified.

## Alternatives considered

A new private key inside every credential envelope, protected by a separate
master key, was considered during this uncommitted work. It adds key material
and lifecycle responsibilities without a deployed compatibility requirement.
Direct protection of a fixed hybrid private key meets the requested storage
boundary with fewer persistent parts.

Platform-only payload encryption would not satisfy the requested hybrid
encapsulation on every platform. X-Wing supplies that composition through the
library rather than application-written cryptographic primitives.

## Consequences

The format is introduced once, with no readers or upgrade paths for earlier
unpublished experiments. Existing plaintext configuration and backup imports
remain migration inputs. Ordinary ZIP exports contain neither credentials nor
private keys. A configuration-independent recovery entry allows explicit reset
of unreadable credentials while preserving scheduling plans and other settings.
It retains usable keys and credentials, quarantines unreadable ciphertext and
only repairs missing or damaged default keys after confirmation. Users then
restart and re-enter credentials.

An optional password-protected business-credential backup avoids requiring users
to migrate system-bound private keys. Fixed-cost scrypt derives an AES-256-GCM
key from the export password; the destination decrypts that package and encrypts
its values under its own hybrid private key. The access token remains local.
This transfer file contains no source private key and does not change the local
hybrid encryption choice. The subsystem description owns validation, scope and
rollback requirements. Password recovery, routine key rotation and a separate
manager key hierarchy remain outside this implementation.

The fixed recipient key does not provide forward secrecy against later private-key
compromise. A process that can read that key or access the protecting system
service can decrypt the credentials. X-Wing is distinct from the similarly named
TLS group, and this work does not configure HTTPS.

The [runtime guide](../../../../docs/cookbook/packaging.md#credential-encryption-runtime)
owns backend requirements and capability checks. Its macOS Intel source-build
requirements and Android Debian ARM64 deployment boundary apply to this choice.

## Verification

The recovery and password-backup addition passed a combined 337 focused backend
cases with two POSIX-specific skips on Windows. This run includes credential
storage, password transfer, route admission, recovery and profile-request tests.
After adding manual desktop recovery without stdout, the recovery suite passed
50 cases; its combined run with CI-scope selection passed 82 cases. Four related
frontend suites passed 28 cases, and the settings-search model suite passed 81.
Credential exclusion in ordinary backups passed 24 focused cases. Desktop
lifecycle, shutdown, Docker credential bootstrap and HTTP logging passed 51 cases
and 50 subtests. These groups overlap and are not an aggregate test count.

Review corrections cover stale-page generation checks, preservation of unset
configuration defaults, multipart size handling, token-dependent Yituliu metadata,
user-wide system-service initialization locking, recovery shutdown during an
active transaction, and a usable frozen desktop recovery entry without a console.
The native GUI, macOS/Linux system services and Docker/Android runtime boundaries
remain unverified locally; isolated substitutes and CI registration do not claim
native execution on those platforms.

The core, provider and [hybrid credential tests](../../../../arknights_mower/tests/credential_store_hybrid_tests.py)
passed 65 cases, with two POSIX-specific skips on Windows. Coverage includes
fixed-key reuse with fresh ciphertext, real Windows DPAPI, six concurrent
processes sharing initialization, tampering and wrong-key rejection, explicit
original-key-file recovery, missing-key refusal and byte-preserving rollback.
macOS Keychain and Linux Secret Service use isolated substitutes.

Network, Token, manager, Yituliu, standalone access and header tests passed
356 cases and 50 subtests. The affected Python checks passed Ruff. These results
belong to the fixed-private-key implementation; results from earlier unpublished
formats are not carried forward as its verification.

Software-update and profile-request tests passed 168 cases and 172 subtests,
with one skip. Their combined run exposed six manager-connection test failures
from reading UTF-8 fixture files with the Windows default encoding. Explicit
UTF-8 reads in that test file produced 69 passing cases on its separate rerun;
the production reader already used UTF-8. Ruff passed for the 22 affected Python
files, and the Git whitespace check passed.

Configuration, backup, profile, Docker credential and build-capability tests
passed 498 cases and 14 subtests, with only the existing duplicate ZIP-member
warning. These are separate coverage groups, not an aggregate count of distinct
tests.

No actual user configuration was migrated. Native macOS and Linux credential
services, Docker images and Android rootfs were not run locally. Corresponding
build paths have a native cryptographic capability check; those checks do not
replace platform execution.
