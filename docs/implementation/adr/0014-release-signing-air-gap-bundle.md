# ADR-0014 — Release signing for the air-gap bundle: identity, trust root, custody, rotation, and the verifier

- **Status:** **Proposed for operator adoption** (2026-10-05). Not built: the build is register F18.3, after adoption. The install and bootstrap UX v0.3 (§5.1, ledger IBU-13) left "exact organizational key custody/rotation" to "a release-engineering policy/ADR"; this is that ADR. Probes P1 and P2 were run on the Rocky 8.10 reference host on 2026-10-05 (`evidence/0014-p1-sshsig-rl8.out.txt`); P1 decided the verifier's shape (D1, D7): the host's OpenSSH cannot verify signatures, so AEW's own verifier does. P3 remains for the build.
- **Resolves:** install UX v0.3 §5.1 (who signs, what, with which trust root); T10's open question 3 ("who signs, and is a detached signature over the manifest enough"); the register's F18.3 note ("key custody and rotation can be a release-engineering ADR"). It does not change the bundle's contents or the install workflow (IBU-12), only how the bundle is signed and verified.
- **Basis:** install UX v0.3 §5 and §5.1; the air-gap research §7 ("Offline bundle and qualification", "Cold-start acceptance"); T10 v0.1 §5 (the bundle's first shape) and §12; ADR-0005 (what a credential is in AEW, and what this key is not); ADR-0009's custody rules (no secret in a model-controlled process); the dashboard design note §4.13 (build provenance: a clean detached checkout of an agreed commit, CI rebuild-verify); the Rocky 8.10 reference host (OpenSSH 8.0p1, Python 3.11.13, `tarfile` extraction filters present since 3.11.4); the SPT py311 wheelhouse facts in `pyproject.toml`.
- **Nature:** a release-engineering decision with a security boundary in it. The verifier is the only code that reads a bundle before anything in it is trusted, so its rules are stated here as requirements, not left to the build.

## Context

An air-gapped organization receives `aew-bundle-<version>-rl8-py311.tar` by hand: no registry, no network, no transparency log, and no way to ask the publisher anything at install time. Whatever the bundle says about itself is untrusted until a signature checks out against a key the organization already holds. The bundle also carries executables (the qualified harness binary) and wheels that `pip` will install, so a hostile or corrupted archive is a code-execution path on the host, and the verifier must refuse it before extracting, importing or executing anything from it.

Three constraints shape the choice of mechanism:

1. **The verifier runs before AEW exists on the host.** It cannot import PyYAML, jsonschema or anything from the bundle; it has the host's Python 3.11 standard library and the host's base tools.
2. **The reference host is Rocky Linux 8.10.** Its base system has OpenSSH 8.0p1 (`openssh-8.0p1-29.el8_10`), OpenSSL 1.1.1k, GnuPG 2.2.20 and Python 3.11.13 from AppStream. Anything newer is itself something to be transferred and trusted. Measured (P1): that OpenSSH build has **no `ssh-keygen -Y`** (`unknown option -- Y`), so the host cannot sign or verify sshsig signatures with its own tools; and (P2) its Python has `tarfile`'s extraction filters.
3. **The repository is public.** A CI secret is one workflow edit away from any branch; a signing key must never be where a workflow can reach it.

What is not in question: the bundle's manifest commits to every consumed artifact (IBU-12); the signing key is release authority, not an ADR-0005 credential, and the runtime never holds it (IBU-13); installation consumes only verified, listed artifacts (IBU-13).

## Decision

### D1. Signature scheme: OpenSSH signatures (sshsig) with an Ed25519 key, in the namespace `aew-bundle`, verified by AEW's own verifier

The manifest is signed with `ssh-keygen -Y sign -n aew-bundle` on the release operator's machine (any OpenSSH from 8.1 on, or a hardware-backed key through it) and verified by AEW's own standard-library verifier (D7), which parses OpenSSH's sshsig envelope (`PROTOCOL.sshsig`: the `SSHSIG` magic, version 1, the public key blob, the namespace, the hash algorithm and the signature over `magic || namespace || reserved || hash_algorithm || H(message)`), checks the key against an `allowed_signers` file, and verifies the Ed25519 signature (RFC 8032) in pure Python. The signature is a detached file beside the manifest (`aew-bundle.json.sig`, the armored sshsig format). Only `ssh-ed25519` keys are accepted: an `allowed_signers` entry of any other key type is refused, and so is a signature whose key blob is not `ssh-ed25519` or whose hash algorithm is not `sha512`.

Why this format and not the alternatives (§"Alternatives considered"): it has domain separation built in (a signature made in another namespace, for another purpose, never verifies as a bundle signature); the trust root is a one-line-per-key text file that an organization can read, diff and keep under its own configuration management; keys can live in `ssh-agent` or, later, in hardware; it is the mechanism `git` already uses for signed commits, so release operators know it; and an organization with a newer OpenSSH can cross-check any bundle with `ssh-keygen -Y verify` itself. Why AEW's own verifier and not the host's `ssh-keygen`: the Rocky 8 base OpenSSH has no `-Y` (P1), and a verifier that depends on no host tool has no `PATH`, version or packaging drift to reason about; the price is about two hundred lines of integer arithmetic that verification (which handles no secret) can carry safely, tested against RFC 8032's vectors and against real `ssh-keygen` signatures (D9).

The namespace is fixed: `aew-bundle` for bundle manifests, `aew-bundle-rotation` for rotation statements (D6). The verifier holds the namespace as a constant; it never takes it from the bundle.

### D2. What is signed: the canonical manifest, which commits to everything consumed

The signed object is the manifest's **exact bytes**. The verifier hashes and verifies the file as it is in the archive and never re-serializes it before checking; canonical form matters for reproducibility (two builds of the same inputs produce byte-identical manifests), not for verification.

The manifest is **canonical JSON**, `aew-bundle.json`, not YAML: the verifier has no YAML parser before AEW is installed, and JSON has a well-defined canonical form in the standard library (`json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=True)` plus one trailing newline, UTF-8, LF). This renames the install design's illustrative `aew-bundle.yaml`; nothing else in IBU-12 changes.

The manifest records, under `schema: "aew/bundle-manifest/v1"`:

- `bundle`: `name` (equal to the tar's file name without `.tar`), `aew_version`, `spec_set`, `source_commit`, `source_tree`, `built_at`, `builder` (`tools/release/bundle.py` and its version), `platform` (`os`, `arch`, `glibc`, `python_tag` `cp311`, `manylinux` tag), `member_count` (every tar member, the manifest and signature included).
- `harness`: each qualified pin with `name`, `version`, `path`, `sha256`, `schema_fixture_sha256` and the `aew/harness-qualification/v1` id it satisfies (install UX §3.1); nothing unqualified.
- `files`: every other consumed artifact, sorted by path: `path` (relative, normalized, forward slashes), `type` (one of `wheel`, `binary`, `catalog_seed`, `skill`, `doc`, `requirements`), `size`, `sha256`, `mode` (`0644` or `0755`).
- `install`: the `requirements` entry's path (a `pip` requirements file with `--hash` pins for every wheel, itself listed and hashed), and the venv layout.

The manifest lists every member of the tar except itself and its signature. A member the manifest does not list is a refusal, not a warning (D7). The tar's own SHA-256 is published beside it for transport integrity; it is not what the signature binds, and it is not what the verifier trusts.

### D3. The trust root: an `allowed_signers` file provisioned independently of the bundle

The trust root is an OpenSSH `allowed_signers` file holding exactly the release principals:

```
release@aew namespaces="aew-bundle,aew-bundle-rotation" ssh-ed25519 AAAA…
```

with optional `valid-after="YYYYMMDD"` and `valid-before="YYYYMMDD"` options, and a `revoked_keys` file beside it (D6). The verifier parses this syntax itself (the principal, the `namespaces`, `valid-after` and `valid-before` options, the key type and the key; anything else in an entry is a refusal) and honours the validity window against the bundle's `built_at`, so rotation does not depend on the host's OpenSSH. The subset is OpenSSH's own, so the same file works with `ssh-keygen -Y verify` on a host that has it.

- The organization receives the key's fingerprint (`SHA256:…`) through a channel independent of the bundle **and** of the repository: directly from the release operator, confirmed out of band (a second channel, or in person), and keeps its own `allowed_signers` under its configuration management at a host path of its choosing (`/etc/aew/allowed_signers` by convention). The repository publishes the same material under `release/allowed_signers` and `docs/release/trust-root.md` as a **cross-check only**: a repository that has been tampered with can change both the bundle and the published key, so the repository copy is never the sole source.
- The verifier takes the trust root's path from an explicit argument or the host's configuration, never from inside the bundle or the staging directory, and refuses a trust root that is writable by anyone but its owner or that lists a key type other than `ssh-ed25519`.
- Provisioning the trust root is the organization's acceptance step for a release identity; `aew doctor --bundle` records which key verified the bundle (D8), so an organization can later tell which hosts accepted which key.

### D4. Identity and custody of the signing key

- One dedicated Ed25519 key per release identity, principal `release@aew`, comment `aew-release-<year>`; generated by the release operator with `ssh-keygen -t ed25519 -a 100` and a passphrase, offline from any agent session. Never a personal login key, never a key that also authenticates to a host or a forge.
- The private key lives only on the release operator's own machine: an encrypted key file plus `ssh-agent`, or the operating system's keychain. It is never in the repository, in a CI secret, on the Rocky 8 VM, in a container image, in a build directory, or in any process that runs or hosts model-controlled code. The ADR-0009 custody rule applies to it as to every secret: no model-controlled process ever possesses it.
- Hardware-backed keys are preferred as soon as every verifying host can check them: FIDO2 `sk-ssh-ed25519` signatures need OpenSSH 8.2 or later on the verifier, which Rocky 8's 8.0p1 lacks, so v1 uses a software Ed25519 key. A PKCS#11 (HSM) key produces an ordinary `ssh-ed25519` signature and may be used from the start where one exists. Moving to a hardware key is a rotation (D6), not an ADR change.
- The key signs bundle manifests and rotation statements, nothing else: no commits, no tags, no other artifacts. Reusing it elsewhere widens what a leaked signature could mean.

### D5. Who signs, and where: the release operator, from a clean checkout, never CI

- `tools/release/bundle.py build` is deterministic: it runs from a clean detached checkout of the tagged release commit (the same provenance rule as the dashboard's static build, design note §4.13), downloads wheels by hash into the wheelhouse for `cp311` / the manylinux tag compatible with glibc 2.28, takes harness binaries from their qualified pins by URL and SHA-256, generates any catalog seed from a clean disposable instance of the exact pin (install UX §5), writes the canonical manifest, and writes the tar with sorted members, fixed `mtime` (`SOURCE_DATE_EPOCH` = the commit's time), `uid`/`gid` 0, no user names and normalized modes, so two builds of the same commit produce the same tar and manifest digests.
- CI's release job builds the bundle and publishes the **manifest digest and tar digest** only. It holds no key and signs nothing. The release operator rebuilds locally, compares both digests with CI's (rebuild-verify, as for the static build), inspects the manifest, and only then signs.
- `tools/release/bundle.py sign` is a separate command from `build`. It refuses to run when `CI` or `GITHUB_ACTIONS` is set, when the key path is inside the repository or the build directory, and when the manifest's digest does not match the one `build` recorded. It never prints or copies the key; it invokes `ssh-keygen -Y sign` and leaves key handling to OpenSSH and the agent.
- Why not CI signing: the repository is public; a secret available to a workflow is available to any branch that can change the workflow, and a protected environment with required reviewers is a later decision that this ADR does not make. The operator's machine is the root of trust, stated as such.

### D6. Rotation, revocation and compromise response

- **Scheduled rotation** every twelve months, and on any of: suspected exposure, the release operator's machine being rebuilt or lost, a change of release operator, or a move to a hardware key.
- **Procedure:** generate the new key (D4); publish `release/rotation-<date>.json` naming the old and new fingerprints, the date and the reason class, **signed twice** in the namespace `aew-bundle-rotation`: by the old key (continuity) and by the new key (possession); announce the new fingerprint through the independent channel (D3). Organizations add the new entry to `allowed_signers` (with `valid-after` where supported) and remove the old one at the end of the overlap. The overlap is at most 90 days; during it both keys verify, and new bundles are signed with the new key only.
- **Revocation:** a revoked public key is added to `revoked_keys` (a plain list of public keys, passed to `ssh-keygen -Y verify -r`) and removed from `allowed_signers`; the verifier refuses a signature by a revoked key whatever its date. A compromise additionally produces an advisory under `docs/release/advisories/` listing by manifest digest every bundle the key signed, and those still supported are rebuilt and re-signed with the new key. Hosts match the advisory against the fingerprint their acceptance record stored (D8).
- **Loss without compromise** (the key is gone, no evidence of exposure): rotation as above, with the rotation statement signed by the new key only and the independent channel carrying the explanation; organizations are told the continuity signature is absent and why.
- A rotation never changes the namespace, the manifest schema or the verifier; it is data, not code.

### D7. The verifier: order of operations and refusal rules

`tools/release/verify_bundle.py` is a single standard-library-only Python 3.11 module, also importable after installation (`aew.release.verify`) for `aew doctor --bundle`. It is transferred with the trust root through the organization's own channel and pinned there like the trust root is; the copy inside the bundle is never the one that runs first. Its steps, in this order, and nothing from the archive is parsed, extracted or executed before step 5 succeeds:

1. **Trust root.** Refuse unless the `allowed_signers` path (and `revoked_keys`, if given) is readable, owned by the invoking user or root, not writable by group or others, and lists only `ssh-ed25519` keys (`TRUST_ROOT`).
2. **Archive shape.** Open the tar read-only as an uncompressed tar (`r:`; compressed tars are refused: fewer decoders in the trusted path, and the bundle is large anyway). Enumerate members **without extracting**. Bounds: at most 10,000 members, declared sizes summing to at most 8 GiB, member names at most 255 bytes (`BUNDLE_BOUNDS`).
3. **Member rules**, each member: a regular file or a directory and nothing else (symbolic links, hard links, devices, FIFOs and GNU sparse or long-name extension records are refused: `BUNDLE_TYPE`); a relative path whose components contain no `..`, no `.`, no empty component, no NUL, no backslash, no control character and no leading `/`, and that does not change under `os.path.normpath` (`BUNDLE_TRAVERSAL`); no duplicate names, compared case-insensitively as well, so a case-insensitive staging filesystem cannot merge two members (`BUNDLE_DUPLICATE`).
4. **The two root files.** Exactly one `aew-bundle.json` (at most 4 MiB) and one `aew-bundle.json.sig` (at most 16 KiB) at the archive root; both are read into memory from the archive (`BUNDLE_SHAPE`).
5. **Signature**, in process, with no subprocess and nothing written to disk: decode the armored sshsig envelope (refusing anything but version 1, an `ssh-ed25519` key and `sha512`); require the namespace to be exactly `aew-bundle`; find the key in `allowed_signers` by its blob under the principal `release@aew` with `aew-bundle` among its namespaces and `built_at` inside its validity window, and require its absence from `revoked_keys`; recompute the signed data from the manifest bytes and verify the Ed25519 signature. The key's fingerprint (`SHA256:` of the blob, OpenSSH's form) is recorded (`BUNDLE_SIGNATURE`).
6. **Manifest.** Parse the verified bytes as JSON; validate the structure strictly (every required key present, no unknown keys, types and enumerations as D2 states, paths obeying step 3's rules, `files` sorted and unique by path, `member_count` equal to the archive's) (`BUNDLE_MANIFEST`).
7. **Cross-check.** The set of listed paths equals the set of regular-file members minus the two root files (`BUNDLE_UNLISTED`, `BUNDLE_MISSING`); each listed entry's member has the declared type and size; each member is streamed and hashed reading at most `size + 1` bytes, and the digest equals the manifest's (`BUNDLE_MISMATCH`).
8. **Extraction**, only now, into a fresh staging directory the verifier creates (mode 0700, empty), with `tarfile`'s `data` filter as a second line of defence; then every extracted file is hashed again from disk and compared, and modes are set from the manifest (`BUNDLE_MISMATCH` again on any difference).
9. **Record.** `verification.json` in the staging directory: the manifest digest, the tar digest, the signing key's fingerprint, the trust root's digest, the verifier's version and the time. `aew doctor --bundle` includes it in the acceptance record (D8).

Any refusal removes the staging directory, leaves nothing else on disk, names its code and the offending member or field (never the member's contents), and exits non-zero. The verifier has no option that skips a step.

### D8. Installation consumes only verified artifacts, and doctor records the acceptance

- `pip install --no-index --find-links <staging>/wheelhouse --require-hashes -r <staging>/<requirements>`: the requirements file is a listed, hashed artifact, so every wheel is checked twice, by the verifier against the manifest and by `pip` against the requirements file's hashes. Nothing outside the staging directory is consulted.
- The harness binary is copied to the versioned install location with the manifest's mode; its SHA-256 and qualification id go into the host's harness qualification record; nothing is executed before `aew doctor` runs the dry probe with the network unshared (install UX §5).
- `aew doctor --bundle <staging> --json` re-runs the verifier (D7) and emits the acceptance record: `verification.json`'s content, the ABI and platform checks, `bwrap` and user namespaces, the harness pin and schema fixture, and the no-hidden-fetch result. The record names the signing key's fingerprint, so a later advisory (D6) can be matched to hosts.
- Tool upgrade and project migration stay separate, as IBU-12 says; the acceptance record is per tool environment, and a project's `aew migrate --plan` does not read it.

### D9. Interoperability: the verifier agrees with OpenSSH in both directions

Because the verifier implements the format itself, the build proves it agrees with OpenSSH: every signature `ssh-keygen -Y sign` produces for the test corpus verifies in AEW's verifier, and every signature AEW's verifier accepts is accepted by `ssh-keygen -Y verify` with the same `allowed_signers` file on a host that has `-Y` (CI's runners do), and the refusals agree (another namespace, a tampered byte, a key missing from the trust root, a revoked key, an expired validity window). The Ed25519 arithmetic is tested against RFC 8032 §7.1's vectors, including the ones with non-canonical encodings a lax implementation accepts. Verification handles no secret, so constant-time behaviour is not required of it; the signing side is OpenSSH's. Should a future verifying host carry an OpenSSH with `-Y`, the organization may cross-check with it, but AEW's path does not change.

## Alternatives considered

- **OpenPGP (`gpg2 --verify`).** Present on Rocky 8 too, and familiar. Rejected for v1: the trust model needs to be fenced off at every call (`--no-default-keyring`, a dedicated keyring, `--trust-model always`, parsing `--status-fd` for `VALIDSIG` and the exact fingerprint), the keyring is binary rather than a reviewable text file, and there is no namespace, so a signature over some other `aew-bundle.json`-shaped file by the same key would verify. Everything OpenPGP gives here, sshsig gives with less surface.
- **Sigstore / cosign (keyless, transparency log).** Rejected: verification needs the log and the identity provider, which an air-gapped host does not have; an offline bundle of the log's inclusion proofs is a transfer-and-trust problem of its own.
- **Verifying with the host's `ssh-keygen -Y verify`.** The first draft of this ADR; rejected by measurement (P1): the Rocky 8 base OpenSSH has no `-Y`. Had it, the verifier would still have carried a `PATH`, version and output-parsing dependency that an in-process verifier does not.
- **Raw Ed25519 with an AEW-defined envelope.** Rejected: it would make AEW the author of a signature format and give the signing side its own key handling, where OpenSSH's envelope is specified, its signing is audited and hardware-capable, and newer hosts can cross-check it (D9).
- **Signing the tar instead of the manifest.** Rejected: the signature would bind bytes the verifier never fully interprets, and a tar can contain what a manifest never lists. Signing a manifest that lists every member, with unlisted members refused, binds the same bytes with the structure visible.
- **Signing in CI with a protected environment.** Deferred: it needs required reviewers and an environment secret with a hardware-bound or rotation-bound story that the public repository does not have today. The operator's machine is the stated root of trust until that decision is made.
- **Shipping the verifier only inside the bundle.** Rejected: the first verification must run code that was trusted before the bundle arrived. The verifier travels with the trust root.

## Consequences and limits

- The verifying host needs nothing but its Python 3.11: the verifier parses the archive, the envelope and the trust root and verifies the signature itself. AEW therefore owns about two hundred lines of verification arithmetic and the interoperability tests of D9 that keep it honest.
- The signature covers the manifest; the manifest covers every consumed member; the verifier refuses unlisted members. Tampering with the tar outside the manifest therefore has no effect except refusal. The tar digest is published for transport checks, not trusted.
- There is no timestamping and no transparency log: an organization learns of a revoked key through the independent channel and the advisory, not from the bundle. The acceptance record's fingerprint is what makes an advisory actionable.
- The threat model is ADR-0005's: a process running as the installing user, or root, on the verifying host is out of scope. What this ADR closes is a hostile or corrupted bundle, a bundle signed by the wrong key, a signature re-used from another purpose, a stale key after rotation, and a leaked CI secret.
- The release operator's machine is the root of trust. Its compromise is a key compromise (D6). A hardware key reduces the blast radius to the machine's session and is the planned next step.
- No SBOM, no per-wheel provenance beyond `pip`'s hash pins, and no signature over the spec pin separately from the manifest; each is a later addition to the manifest schema, not a change to this ADR.

## Probes before the build

- **P1 (run 2026-10-05; decided D1 and D7).** On the Rocky 8.10 reference host, `openssh-8.0p1-29.el8_10`: `ssh-keygen -Y sign`, `-Y verify` and `-Y check-novalidate` all fail with `unknown option -- Y`. The host cannot verify sshsig signatures with its own tools, so the verifier does it in process (D7 step 5). Script and output: `evidence/0014-p1-sshsig-rl8.sh`, `evidence/0014-p1-sshsig-rl8.out.txt`.
- **P2 (run 2026-10-05).** `python3.11-3.11.13-7.el8_10` has `tarfile.data_filter`. Under the `data` filter it **refuses** `../` traversal, a symbolic link to an absolute target, a hard link outside the destination, a FIFO and a character device, but it **neutralizes rather than refuses** an absolute member path (`/etc/evil` is extracted as `etc/evil`) and a setuid mode (`4755` becomes `0755`). That is why the filter is only the second line: the verifier's own rules refuse those members outright (D7 step 3), and a bundle that needed the filter's help would already have failed. Same evidence file.
- **P3 (for the build).** `pip` on the same host accepts the wheelhouse's manylinux tag for every wheel with `--require-hashes` and `--no-index`, and `python3.11 -m venv` plus that install needs nothing outside the staging directory (an `strace`-style or proxy-log check of the install step itself, as install UX §5 does for the harness start).

## What the build must show (F18.3)

- **An adversarial-archive test per refusal rule of D7**, each archive built by the tests themselves: `..` and absolute paths, a path that normalizes differently, backslashes, NUL and control characters, a symbolic link, a hard link, a device, a FIFO, a sparse member, a duplicate name, a case-insensitive duplicate, an unlisted member, a listed member that is missing, a size one byte short and one byte long, a hash mismatch, a type mismatch, a mode not in the enumeration, a manifest with an unknown key, a manifest changed by one byte, a signature by another key, a signature by the right key in another namespace, a revoked key, a trust root writable by others, a trust root listing an RSA key, a compressed tar, and member-count and total-size bounds exceeded. Each must fail with its named code, extract nothing, and leave no staging directory.
- **The signature verifier:** RFC 8032 §7.1 vectors pass; the interoperability corpus of D9 agrees with `ssh-keygen` in both directions, acceptances and refusals; a malformed envelope (wrong magic, version 2, an RSA key blob, `sha256`, truncated fields, trailing bytes) is refused; a malformed `allowed_signers` entry (unknown option, a second key type, a missing namespace) is refused.
- **Determinism:** two builds of the same commit produce identical manifest and tar digests, on Linux CI and on the Rocky 8 host.
- **The signing command's refusals:** under `CI`, with a key inside the repository, and with a manifest whose digest differs from the build's.
- **Rotation:** a trust root with two keys verifies bundles signed by either during the overlap; a rotation statement verifies under both keys in its own namespace; a revoked key fails whatever `allowed_signers` says.
- **The end-to-end install on the Rocky 8 host**, run by the operator (the agent never uses the host's sudo): verify, install, `aew doctor --bundle --json`, and the acceptance record naming the fingerprint. This is the host acceptance record IBU-12 asks for.
- **Secret scan and custody:** the release key never appears in the repository, CI logs, the bundle or the acceptance record; the existing credential scans extend to the key's file forms.
