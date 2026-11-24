**Built (`fix/probe-without-ipv6`).** The probe's `attempt()` now creates its socket inside its handled region, so a
kernel that refuses the family records the error's name for that route (EAFNOSUPPORT for `direct6`), which the host's
judge already accepts. A creation error on another route is recorded too: it fails row 1 for the direct routes
and the bridge (the judge accepts only the named no-route errors there), and for `host_port` and `host_abstract` it
reads as unreachable, which row 1's netns and socket-table checks also cover. The test:
`test_a_host_without_ipv6_records_no_ipv6_route_and_still_passes_row_1` in `tests/unit/test_containment_probe.py`. No
pinned surface covers the probe payload's text, and the generated reference is unchanged.
