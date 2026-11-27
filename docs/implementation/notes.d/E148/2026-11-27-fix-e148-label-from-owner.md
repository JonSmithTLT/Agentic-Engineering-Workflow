F2 of #649's review is fixed: the route's projection no longer reads a run's
containment label itself. It reads it through the label's owner,
`aew.harness.containment.network_facts`, which reads through `normalize` as
`harness status` does, so the two agree on a label of every age. A label
before CS-3b now gives `provider_relay: none`, and a run with no label gives
this platform's network mode with `provider_relay: none`, where the projection
gave null. The relay's vocabulary has one owner, `containment.relay`. The
proposal states the rule.
