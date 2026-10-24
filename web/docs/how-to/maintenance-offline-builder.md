# Dependency maintenance offline builder

This carrier supports the maintenance lock with Vite 8.3.5, Zod 4.6.6 and transitive Undici 7.30.1. It adds no dependency or override. The historical carriers and [packaged frontend baseline](../reference/f20-production-baseline.md) remain unchanged.

Use the full image ID and checksummed export in the [provenance record](../reference/toolchain/maintenance-builder-provenance.json). The supported offline build platform is Linux/amd64 glibc, with Node 22.22.2 and npm 10.9.7. Preserved native package selectors are metadata checks, not runtime validation on other platforms.

```bash
sha256sum aew-web-maintenance-7004847f33bf.tar
docker load --input aew-web-maintenance-7004847f33bf.tar
docker image inspect sha256:f63a4e3d892d50147c364a9b57cb97af840e2c0212558da43d53794b38882c45
SPT_FRONTEND_IMAGE=sha256:f63a4e3d892d50147c364a9b57cb97af840e2c0212558da43d53794b38882c45 bash web/scripts/offline-gate.sh
```

The gate installs with network access and lifecycle scripts disabled, then checks the dependency graph, contracts, generated types, documentation, types, lint, tests and production/demo/STG-02 builds. Acceptance evidence must use the [committed-source freeze procedure](verification.md), not an uncommitted tree or the carrier's staging baseline.

The carrier contains the package pair, registry cache, `frontend-npm-manifest.json` and `SHA256SUMS` under `/opt/spt-frontend`. Cache preparation was connected and pinned by package integrity; installation and image construction were offline. Eleven native libc selectors lost during npm lock generation were restored from integrity-verified published package manifests. Package identities and all native os/cpu/libc selectors were compared against the baseline. Pages and browser fixtures do not establish production integration.

To reproduce the [recipe](../../scripts/offline-builder-maintenance.Dockerfile), supply the checksummed staging context named in the provenance record. Verify the local `aew-web-builder-base:14e051132580` alias resolves to the recorded immutable base before building. Pass the recorded lock hash as `AEW_FRONTEND_LOCK_SHA256`; use `--network none --pull=false`. The historical base and its exports must remain available.

Mainline packaging is a separate step: agree the exact validated source commit, rebuild production from its clean tree, import the build and complete build manifest together, verify their hashes, then run authenticated live acceptance. This carrier does not select a new package baseline or change accepted/provisional wire contracts.
