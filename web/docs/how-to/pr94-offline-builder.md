# PR94 dependency builder

Use this carrier for the corrected PR94 lock. The historical [builder](pinned-web-builder.md) and [provenance](../reference/toolchain/builder-provenance.json) remain unchanged for older freezes and the agreed [F20.5 package baseline](../reference/f20-production-baseline.md).

| Identity | Value |
|---|---|
| Image | `sha256:14e051132580dc72266926a9c91023e1be7f71211c0086dd5e5a4d9252360b8b` |
| Platform | Linux/amd64 glibc |
| Toolchain | Node 22.22.2 / npm 10.9.7 |
| Lock SHA-256 | `0eaba7ab3e6b2df60cc72d72cc6ad0c7d8537c3ec94369e0e593517976b4a9fe` |
| Carrier runtime checkpoint | `7fed3028b9152e0345130824479d7eddb05d52ea` |
| Export | `aew-pr94-builder-7fed302.tar` |
| Export SHA-256 | `2f18d031cbc367a5617df64514202477847c1c9b4a4e9c6b4bf3f2aadd50aa9e` |

The image and export are staged in Ubuntu WSL's Snap Docker engine. Docker Desktop has a separate store. Request the named carrier archive when reproducing on another engine; verify its SHA-256 before loading, then inspect the full immutable image ID. Its cache is not a promise of offline support for musl/Alpine, ARM, Windows or Darwin.

```bash
sha256sum aew-pr94-builder-7fed302.tar
/snap/bin/docker load --input aew-pr94-builder-7fed302.tar
/snap/bin/docker image inspect sha256:14e051132580dc72266926a9c91023e1be7f71211c0086dd5e5a4d9252360b8b
PATH=/snap/bin:$PATH SPT_FRONTEND_IMAGE=sha256:14e051132580dc72266926a9c91023e1be7f71211c0086dd5e5a4d9252360b8b bash web/scripts/offline-gate.sh
```

If the Snap daemon is stopped, start it with `sudo snap start docker` and wait for `/snap/bin/docker info` to succeed. The gate installs offline with scripts and networking disabled, then checks the complete dependency tree, contracts, generated types, tests and both builds. Freeze evidence from an explicit clean committed tree using the [existing procedure](verification.md); the staging checkpoint above is not interchangeable with the final source commit recorded by that freeze.

The carrier contains `/opt/spt-frontend/package/`, `frontend-npm-manifest.json`, the npm cache and `SHA256SUMS`. The [provenance record](../reference/toolchain/pr94-builder-provenance.json) pins their hashes. Rebuilding uses the [recipe](../../scripts/offline-builder-pr94.Dockerfile) with that checksummed staging context and the historical base image; first verify that the local base tag resolves to its recorded immutable ID. Do not substitute a floating registry image or perform a fresh unpinned install.

PR94 adopts React Router DOM 7.18.4, Vite 8.3.2 and **Vitest 5.0.3**. The operator explicitly authorized retaining the major Vitest upgrade and proceeding with this corrected dependency adoption on 2026-10-06, conditional on validation and merge gates. The correction restores the published musl-only restriction on one existing native package; versions and package integrity values remain unchanged.

This adoption does not update the Python package's frontend or approve a new packaging commit. That separate rollout needs an agreed source commit, a clean production rebuild and authenticated live acceptance. No accepted or provisional API contract is changed.
