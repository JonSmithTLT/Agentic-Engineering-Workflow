**STG-05 CS-3a (2026-10-24): R-6's predicate and F28's egress proxy, built and not yet wired.** CS-3, F28's network
containment, is built in two pull requests (the designer's split, 2026-10-24). This first one adds two modules and
wires nothing into a launch, so no run's network, behaviour or label changes. Linux runs stay `shared`, and F28's
condition stands: nothing may call Linux runs network-contained before its live lane passes.

- **`aew.harness.containment.peer`** is ruling R-6's one owner.
  - `host_route` refuses loopback, link-local and host-local addresses: "this host" (`0.0.0.0/8`, `::`), and every
    address the kernel delivers to this host, whatever route makes it local. That is an address that binds, or one a
    `local` or `anycast` route covers in any of the kernel's routing tables, in either family. Tables that cannot be
    read count as local.
  - It judges IPv4-mapped, IPv4-compatible and NAT64 forms by the IPv4 address they carry too.
  - It judges addresses, never names.
  - `not_public` is the any-public-address policy's test.
- **`aew.harness.containment.egress`** is F28 §3.4's credentialless, CONNECT-only proxy.
  - Its two policies are a bounded `host:port` allowlist (the workers') and any public address (the Lead's, which
    CS-4 selects). R-6 applies under both: before the connect, and again on the connected peer.
  - One refused answer refuses the whole name.
  - The whole request head has one deadline.
  - A tunnel ends both ways when either side ends it.
- **Stricter than the hand-off, and accepted by the Lead:**
  - R-6 also refuses `0.0.0.0/8` and `::`.
  - Host-local is whatever the kernel delivers to this host, not a list of interfaces.
  - A name with any refused answer is refused whole.
- **Known limits**, which CS-3b or CS-4 decide where the shim, the proxy's only client, exists:
  - concurrent tunnels are unbounded;
  - an established tunnel has no idle timeout;
  - under `net.ipv4.ip_nonlocal_bind=1`, every address counts as local, so all egress is refused;
  - a `local` route that covers every address, in any table, makes its whole family local, so all of that family's
    egress is refused.
- **Not detected:** a destination that the host's own network configuration rewrites to this host after the proxy has
  judged it. **Precondition:** that configuration is root's; AEW adds none, and no contained process can. **Worst
  case:** a contained process reaches the host service such a configuration names. Everything else R-6 checks still
  holds: the address actually connected is judged before the connect and again on the peer, against loopback,
  link-local, every address assigned to this host, and every local route in any table. The check that would detect it
  is register row F28.1, deferred (operator, 2026-10-24).
- **CS-3b,** after CS-2 merges, wires it in: the AF_UNIX listener and its bind, the shim, the relay, the namespace, the
  label and the self-test row. The label lists this residual: "egress (R-6): a destination the host's own network
  configuration, root's, rewrites to this host is not detected." F28's row has one note, which points here
  ([`../F28/2026-10-23-feat-stg05-cs3a-egress.md`](../F28/2026-10-23-feat-stg05-cs3a-egress.md)). CS-3's later notes
  go here.
