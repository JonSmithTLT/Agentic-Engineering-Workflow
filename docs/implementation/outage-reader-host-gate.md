# Qualify the independent outage reader on a Linux host

**Status:** operator procedure for the A-45 O-02 revision 2.1 release gate, 2026-11-26.

`aew read` reports committed records and named last-known observations. The command's help lists its D-01 0.3.4
profile, including the route destinations. Use `--human` for coverage limits and the reasons for a partial response.
The path parameters ending in `_id` are unpadded base64url of the IDs returned in the result. A list cursor goes in its
route's `cursor` query parameter. Quote a route that contains a query string.

## Prepare

1. Use an installed build from the exact release revision under test and the corresponding source checkout for the
   frozen OpenAPI and fixtures. Use a disposable, authoritative AEW project on the host. Keep its gate outputs in a
   directory outside the project. Keep private host, project and approval details out of the public repository.
2. Record this host's G3-12 containment evidence for the actual Lead and worker launch paths. Qualify only on Linux
   where that evidence still holds. Record Q04 as not run on any other host, and leave its gate open. The same reader
   is available on Windows with `G4_unqualified`.
3. Seed the project through the normal AEW commands. Keep an attached Lead generation, a Ticket with an accepted plan
   and ingested evidence, an invocation, an archived work unit and one waiting or attention item. Keep a second,
   settled project with a vacant Lead and no active invocation for complete and empty lists. Stop the gateway, Lead
   broker, dashboard, worker supervisors, operator endpoint and provider relay. Verify that none is serving the test
   project. Save the exact commands, exit codes and both renderings beside the gate evidence.

For a route ID, run `python -c 'from aew.stg02.wire import b64url; import sys; print(b64url(sys.argv[1]))' ID` with the
installed AEW interpreter. Use the Ticket's ID for work detail, packages, assurance and continuation-state, the
invocation's execution ID for run detail, and the attachment list's `ref.id` for attachment detail. For resolve, use
`/v1/read/resolve?kind=assurance_basis&id=aew:assurance:T-0001&revision=plan-1`, substituting the assurance
item's exact `ref.id` and `ref.revision`. Omit the revision parameter when that ref has no revision.

## Run O02-Q01 to O02-Q08

| Check | Run on this host | Keep with the gate record |
|---|---|---|
| O02-Q01 | At the operator terminal, bind-mount the disposable project's `.aew` onto itself, then remount it read-only. Run `sudo mount --bind "$project/.aew" "$project/.aew"` then `sudo mount -o remount,bind,ro "$project/.aew"`. Verify the mount options with `findmnt -T "$project/.aew/state"` and `findmnt -T "$project/.aew/local"`. Run `aew -C "$project" read "$route"` for each of the twelve served routes with services stopped. Use `sudo umount "$project/.aew"` after Q03. | Mount and service observations, twelve schema-valid answers, exit status and read times. |
| O02-Q02 | With the read-only mount still active, hash the regular files under `.aew/state`, `.aew/local` and the tracked `.aew/` tree before and after exercising all twenty routes and both renderings. Compare file inventories and SHA-256 hashes. Include the Git status before and after. | Both inventories and the equal comparison. |
| O02-Q03 | From the corresponding source checkout, run `python -m pytest tests/unit/test_outage_reader.py -q` with its absolute `src` on `PYTHONPATH`. On the mounted fixture, validate each JSON body against the matching status and response schema in frozen A-25 OpenAPI. The test's `assert_schema` uses the packaged frozen D-01 schema definitions and a date-time format checker. Compare item and field stamps and disclosure to the A-45 tables. | Fixture and command outputs, schema result for all twenty routes, stamp and disclosure check evidence. |
| O02-Q04 | On this qualified containment configuration, use a real Lead session, a real worker run and a process in a real AEW containment layout. In each, run `aew -C "$project" read /v1/read/work` and repeat with `--human`. Keep the operator's terminal as the comparison. | Each contained or session caller's `authentication_unqualified` Problem with the fixed O02-02.e text and an empty disclosure. Capture the operator's successful result separately. |
| O02-Q05 | Use five copies of the project. On each, plant exactly one case before remounting read-only: remove the control file, change a line before its checksum trailer, change a pinned work record, remove that work record, or remove a middle transition record. Run work list, work detail and continuation-state on every copy, recording both renderings. | Missing or corrupt control gives `unavailable` on work and `owner_unavailable` on continuation-state. Failed pins make the affected results partial, distinguish stale from unavailable field stamps and suppress unverified text. A transition gap is partial. Compare hashes before and after each read. |
| O02-Q06 | Run comparable lists in the settled and attached projects. On the attached project, also observe an actual running writer. Render an empty list for a valid filter in each. Inspect every source stamp, continuity, page membership and limitation. | Complete reads are historical and have unknown membership. An active invocation or attached Lead makes lists partial. Empty results that read the store say “none committed as of.” No output qualifies currency or continuity. |
| O02-Q07 | Plant a distinct inert marker in each O02-04 excluded source on a disposable project and in the G3 client's per-host approval-record location on the test host. Include a run transcript and tool-call log. Run every route in both renderings and search the output for the markers. Clean up the disposable sources after the check. | Zero marker matches. Waiting and attention identify the existing sources they did not read and return the corresponding source limitation. |
| O02-Q08 | With Q01–Q07 passed, prepare the exact S01-30 record as described below. Run a served route before installing it, after installing it on this host, and with the record removed or inapplicable. Restore only the verified file for the host on which it applies. | The comparison shows `G4_unqualified` before, absent only with the current record on the qualifying host, and present again when the record is inapplicable. Attach the comparison as the Q08 evidence. |

The approval record location is `$XDG_STATE_HOME/aew/g3/requests/`, with `~/.local/state` as the default state
directory. The service's own confirmer continues to show pending approvals.

## Record the host gate

Generate a record template with the installed interpreter. Redirect only to the operator's evidence directory.

```sh
python -c 'import json; from aew.stg02.outage_host import record_template; print(json.dumps(record_template(), indent=2))' \
  > "$evidence/g4-qualification.json"
```

Complete the profile, actual harness and provider versions, permitted operations, operator-selected applicability and
evidence issuer. Set `tested_at` and `valid_until` with UTC timestamps. Link the current G3-12 containment evidence
and the file for each of the eight checks. List what invalidates this evidence, including a reader release change,
host kernel or architecture change, change to the qualified harness or provider version or containment configuration,
and the recorded expiry. Include the release revision and exact installed package identity in the evidence. The
template derives the machine and installed AEW binding locally.

Install the completed record as the operator in `$XDG_DATA_HOME/aew/g4/qualification.json` (or
`~/.local/share/aew/g4/qualification.json` when unset). Keep the source evidence in the operator's host evidence
directory. Withdraw the record when an invalidation trigger occurs and qualify the new configuration. The reader only
checks the record and never creates, copies or repairs it.
