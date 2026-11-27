# Dashboard run provider routes

**Proposed for C0 review.** E148's backend projects recorded provider-route
labels. An additive read route lets the dashboard use them while deployed
clients keep their existing `/runs` response shapes. The web contract owner
selects the next version in the 0.1 series and adopts the route through C0.

## Proposed route

`GET /api/v1/runs/{id}/provider-routes` and its corresponding `HEAD` use the
same authenticated read session, invocation identifier, lookup, errors and
cache validation as `/runs/{id}`. There are no query parameters. An unknown
or custody invocation receives 404. An invocation with no runs receives
an empty list. The route's envelope uses the version that adopts it.

The backend returns the same first 250 recorded runs as the invocation detail.
It reads each run's recorded containment label through the label's owner,
`aew.harness.containment.network_facts`, the reading `harness status` uses, so
the route and `harness status` give the same answer for every record. A label
of any age is read as `containment.normalize` reads it: a label written before
CS-3b, whose network is a mode string, has that mode and `provider_relay:
none`; a run with no label, or one written before M4-B, is the uncontained
run's, with `provider_relay: none` and this platform's network mode (`shared`
on Linux, `not_provided` elsewhere). A null value means the field holds a value
outside its closed vocabulary, which no producer writes; it is never passed on.
`provider_relay: none` records that the launch reported no relay. It cannot
establish provider connectivity. `relay_family` describes the recorded
relay-family check for a configured relay.

Only the fields below enter the response. A relay's destination, proxy,
credential configuration, paths and other launch details stay in the run record.

```yaml
RunProviderRoutes:
  type: object
  additionalProperties: false
  required: [invocation, runs]
  properties:
    invocation:
      $ref: '#/components/schemas/OpaqueId'
    runs:
      type: array
      maxItems: 250
      items:
        type: object
        additionalProperties: false
        required: [id, network_mode, provider_relay, relay_family]
        properties:
          id:
            $ref: '#/components/schemas/OpaqueId'
          network_mode:
            enum: [proxy_only, isolated, shared, not_provided, null]
          provider_relay:
            enum: [configured, none, null]
          relay_family:
            enum: [matches, unverified, null]
```

The response data comes from
[`Projector.run_provider_routes`](../../../src/aew/dashboard/projections.py).
After C0 adoption, the server can register the route and validate GET, HEAD,
authentication, and ETag behavior against the adopted contract.
