# Pinned web builder location

The validated image is `sha256:ef83c04ea3f483d4a9c2a945f4669786018fa6ce31757c7f938c930cc2db8407` (Linux/amd64, Node22.22.2/npm10.9.7). It was inspected successfully on2026-10-03 after the W03 review.

It lives in **Ubuntu WSL's Snap Docker engine**, whose data root is `/var/snap/docker/common/var-lib-docker`. Docker Desktop uses a different image store; absence there does not mean the pinned image is missing. Use the Snap CLI explicitly because the default WSL `docker` command can select the Desktop shim.

From Windows PowerShell:

```powershell
wsl -d Ubuntu -u root --exec /snap/bin/docker image inspect sha256:ef83c04ea3f483d4a9c2a945f4669786018fa6ce31757c7f938c930cc2db8407
```

If the Snap daemon is stopped, start it with `wsl -d Ubuntu -u root --exec snap start docker`, then repeat inspection. From the frontend repository root in Ubuntu WSL:

```bash
PATH=/snap/bin:$PATH SPT_FRONTEND_IMAGE=sha256:ef83c04ea3f483d4a9c2a945f4669786018fa6ce31757c7f938c930cc2db8407 bash web/scripts/offline-gate.sh
```

If another Docker engine needs the same carrier, export it from this store with `docker save --output <shared-archive.tar> <immutable-image-id>` using `/snap/bin/docker`, then `docker load --input <shared-archive.tar>` in the destination engine. Inspect the full image ID there before running the gate. Do not replace pinned validation with a fresh image or another Node version.

This note identifies the existing carrier; it does not claim the reviewer reran validation or alter their report.
