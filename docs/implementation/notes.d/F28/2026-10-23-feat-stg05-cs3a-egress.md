**STG-05 CS-3a: R-6's predicate and the egress proxy, built and not yet wired (designer split, 2026-10-24).** CS-3 is
built in two pull requests. This first one adds two new modules and wires nothing into a launch, so no run's network,
behaviour or label changes: Linux runs stay `shared`, and F28's condition stands (nothing may call Linux runs
network-contained before its live lane passes).

- `aew.harness.containment.peer` is ruling R-6's one owner. `host_route` refuses loopback, link-local and host-local
  addresses, the last being "this host" (`0.0.0.0/8`, `::`) and the kernel's local table, read by a bind that is never
  listened on. It judges IPv4-mapped, IPv4-compatible and NAT64 forms by the IPv4 address they carry. It judges only
  addresses, never names. `not_public` is the any-public-address policy's test ("globally reachable"). Both use the
  module's own tables from IANA's special-purpose registries (2025-10-09), not `ipaddress`'s flags, whose answers
  differ between Python 3.11 and 3.13.
- `aew.harness.containment.egress` is F28 §3.4's proxy. It is credentialless and serves CONNECT only, under one of two
  policies: a bounded `host:port` allowlist (the workers') or any public address (the Lead's, which CS-4 selects).
  R-6 applies under both: it runs before the connect, and again on the connected socket's peer address. One refused
  answer refuses the whole name. The relay's exemption is structural: the relay (CS-3b) never goes through this
  proxy.
- **Stricter than the hand-off, and accepted by the Lead:**
  - R-6 also refuses `0.0.0.0/8` and `::`.
  - Host-local is the kernel's local table, not a list of interfaces.
  - A name with any refused answer is refused whole.
- **Known limits:**
  - Concurrent tunnels are unbounded. F28 gives no number; CS-3b or CS-4 decides, where the shim, the proxy's only
    client, exists.
  - Under `net.ipv4.ip_nonlocal_bind=1` every address counts as local, so all egress is refused.
- CS-3b, after CS-2 merges, wires the proxy in: the AF_UNIX listener and its bind, the shim, the relay, the namespace,
  the label and the self-test row.
