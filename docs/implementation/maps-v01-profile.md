# V-01's profile for the built structural maps

**What this is.** The profile register row E293 asks for: which of A-14's project-understanding capabilities V-01
supports with the maps built in `src/aew/maps/` (F22.1, switched on for every card by E62 and E184), at which source
and deployment limits, and, for each A-14 obligation E293 holds the built code against, how far V-01 meets it and the
test that holds it on the built code. A-14 is the adopted contract
([`A-14`](../contracts/A-14/A-14__AEW-P01-Project-Understanding-and-Maps-Contract-candidate-v0.2.1.md), P-01); P-DEC-01
(source and structural orientation first) and P-DEC-02 (maps stay derived and agent-reachable, with no protected map
writer and no custody service) are the operator's first selections of 2026-10-24. This page states what is built; it
adopts nothing and reopens no design. Its state is register E293's: read it with `python tools/register.py show E293`.

## Capabilities (P01-34)

| A-14 capability | V-01 | Where, and at which limits |
|---|---|---|
| Authoritative retrieval | **Not a map capability.** Owners serve their own facts | The pack's typed owner items (the work unit, the accepted plan, the evaluated snapshot, the policy) come from control state, never from a map |
| Structure | **Supported** | One commit's structural record from its Git objects (`aew map generate`), its freshness against a commit, and the Lead's resume row |
| Orientation through the pack slices (the context packet's map share) | **Supported**, behind `maps.pack_slices: structural` (on for a new project, offered to an existing one) | Every worker archetype's pack (E184): a bounded, fenced slice of the selected map, qualified against the work's base |
| Language semantics | Not supported | F22.2, on measured need behind CAPR-B2 (P-DEC-03) |
| Architecture synthesis | Only as a reference: `aew map select-architecture` records an existing discovery record, attributed, never verified | F22 (the architecture map and composed view) is unscheduled |
| Test and constraint locators | Only the structural record's conventional and declared test candidates | F22.3 |
| Impact | Not supported | F30 |

**An absent map degrades to direct source reads and usable work** (P01-34). No selected map, a missing, corrupt or
stale one, or a malformed registry gives the pack one labelled line ("UNAVAILABLE (...): no structural map is used in
this pack. This blocks nothing; navigate from the source.") and never a refused dispatch, gate, transition, launch or
resume: `test_no_map_state_changes_dispatch_gates_transitions_or_resume`, `test_the_pinned_readers_never_raise`,
`test_a_map_that_cannot_be_built_never_fails_init`.

### Source limits

- **One commit's Git objects, never the checkout, index or working tree.** `--commit H` means exactly `H`; replace
  refs and lazy fetching are off; `.aew/` is left out of the listing. A record never describes uncommitted changes.
- **Complete source only.** A missing object refuses generation (`MAP_CURRENTNESS_UNPROVEN`); a partial clone on a
  git older than 2.44, which cannot be stopped from fetching lazily, is refused before any object is read.
- **Bounded reads.** Descriptors are read at depth 2 or less, and every `.gitattributes`; a blob over 256 KiB is not
  read, and reads stop at 2 MiB in total; LFS pointers are recorded, never parsed; symlinks are listed, never read or
  followed; submodules are a path and an object id, never traversed.
- **Bounded sections.** Directories at depth 3 or less, at most 200 rows (the largest), and each other section capped
  (`structural.CAPS`), with every cut counted in the record.

### Deployment limits

- **Storage is local and agent-reachable.** Artifacts and the registry live in `.aew/local/maps/` (git-ignored,
  rebuildable; deleting it means "no selection"). There is no protected producer, ingress or custody (P-DEC-02).
- **Who writes.** `aew map generate` and `select-architecture` are the Lead's; `aew init` makes and selects the first
  map; a Lead's dispatch refreshes a STALE or absent map for the work's base within 10 s (`service.REFRESH_S`), and
  selects it only when the base is the authoritative head. Nothing a worker or a run starts writes a map.
- **Who reads.** Workers read only their pack's slice. `aew map show` and `aew map diff` are the operator's and the
  Lead's. The dashboard's maps routes (F20.8) are not V-01's route: V-01 serves maps to agents only, and the shared
  read wire carries no map read for V-01 (P-DEC-04).
- **What `aew map show --commit H` does.** It shows the selected map (or `--root`'s) with that map's freshness
  compared against `H`; it does not generate or show a map of `H`. A map of `H` is `aew map generate --commit H`
  (stored) or `aew map diff --commit H` (in memory, stored nowhere).

## The slice's bounds

At most `ROWS` (40) directory rows and `HINTS` (20) generated and vendor hints, and a byte budget,
`SLICE_MAX_BYTES` (9 KiB), that cuts hints first and then rows and says so. **The byte budget is nominal, not a hard
ceiling:** the fixed lines (the map, freshness, refresh, directories, incompleteness, unmatched-scope, hints and limits
lines) are never cut, so lines naming very long paths can carry a body past it on their own.
`python tools/perf/map_slice_bytes.py` measures it.

**The Ticket's own directories survive the global cap** (E293, from an external audit). The record keeps the 200
largest directories for the global view; when that cut any and the Ticket's scope is restricted, the slice reads the
rows in scope from the map's own source tree (`slices.scoped_rows`: `ls-tree` of the record's tree, checked against the
record's `path_listing_sha256`, by the generator that made it, within 5 s). When it cannot, the count in scope is a
lower bound and a line says that a directory in scope that is not shown is not absent. A regenerated pack uses the
slice body it pinned, so a later renderer or an unlistable tree never changes it.

## The obligations

Each row names how far V-01 meets the obligation and the tests that hold it on the built code. "Partly" says what is
not met, and why that is V-01's stated limit rather than a defect.

| Obligation | How far V-01 meets it | Held by |
|---|---|---|
| **P01-04** per-consumer identity and snapshot | **Met for committed bases.** The pack names its recipient (the invocation and its role), its work revision (the work unit and the accepted plan) and its source basis (the evaluated snapshot's base); the slice names its map's own commit and its freshness against that same base, never the head's or the map's own. A map selected for one commit is STALE, with its reason, for a Ticket at another. The map is of commits only, so a worker's uncommitted edits are never part of its basis and can never make it CURRENT | `test_the_orientation_names_its_work_revision_source_basis_and_recipient`, `test_a_map_selected_for_one_commit_never_passes_as_current_for_another_base` |
| **P01-06** scoped disclosure and absence | **Met for V-01's inputs.** A map is derived only from the tracked tree of one commit, which every role's workspace already holds, so there is no recipient-restricted input to leak through counts or ordering, and map reads take no service credential. An empty answer is scoped: a scope path no row names is said to be no directory of that commit at the map's depth, and of its tracked paths only. General recipient-scoped disclosure is not built, since no V-01 map holds a restricted input | `test_an_empty_scoped_answer_names_the_commit_and_depth_it_covers_and_nothing_wider` |
| **P01-07** history and currentness, competent renewal | **Met.** Freshness is a comparison of immutable Git objects (the recorded listing and inputs against the base's), computed on read and never written into the artifact; no clock enters it. A pinned slice keeps its commit and the freshness it had against its base, labelled as such, for navigation | `test_no_map_freshness_turns_current_on_a_timer`, `test_the_slice_carries_the_pinned_freshness_with_its_qualification`, `test_with_the_switch_on_every_card_gets_the_slice_and_its_pack_pins_the_map` |
| **P01-08** structural claim ceiling | **Met.** Sections hold shape, tracked paths, language counts, build descriptors and declared or conventional candidates, each labelled with its source; generated and vendor entries are navigation hints, never policy | `test_the_sections_find_declared_and_conventional_facts_and_never_guess` |
| **P01-09** reproducible input set; production claims | **Met, with the claim stated.** The record names its commit, tree, object format, generator and ruleset, every input it read or skipped (the tracked reader's log, never a hand list) and what it cut; its digest and generator name are claims, which is why every reader labels the map `AGENT_REACHABLE_DERIVED` (P01-37) | `test_every_considered_blob_is_an_input_read_or_not_and_nothing_else_is`, `test_mutating_only_an_unrecorded_blob_never_changes_the_record_and_a_recorded_one_always_shows`, `test_generator_output_changes_only_with_a_new_generator_identity` |
| **P01-10** safe input handling | **Met.** Generation, freshness and the scoped listing use Git plumbing over objects only, with hooks off, the fsmonitor off and configured drivers neutralised; no repository filter, textconv, hook or pager runs. Nothing repository-controlled is executed, so nothing needs ADC/HEB authority | `test_reading_or_generating_a_map_never_runs_repository_controlled_code`, `test_a_commit_is_read_from_its_git_objects_never_the_checkout_index_untracked_files_or_replace_refs`, `test_symlinks_submodules_lfs_pointers_and_hostile_names_are_bounded_and_never_followed`, `test_a_blobless_clone_missing_a_descriptor_is_refused_and_never_fetches` |
| **P01-11** structural freshness precision | **Partly.** The listing and recorded inputs are compared with the base's; a missing object, an unknown commit or a partial clone gives UNKNOWN, never CURRENT. Content outside the recorded inputs reads CURRENT because the generator's tracked reader logs every blob it considers, mechanically. The recorded list itself sits in the agent-reachable artifact and is checked only against the artifact's own digest; an independently qualified recomputation (P-DEC-02) is not built | `test_freshness_follows_the_path_listing_the_recorded_inputs_and_the_generator`, `test_an_old_git_partial_clone_is_refused_before_any_object_is_resolved_or_read` |
| **P01-12** bounded outputs (the slices' share; F15.8 owns the rest) | **Met for the slices.** Every count says what it covers; a cap-induced omission is never shown as absence; a Ticket's directories survive the record's cap | `test_a_tickets_small_directory_survives_the_global_directory_cap`, `test_rows_in_scope_the_cap_cut_and_that_cannot_be_listed_are_never_read_as_absent`, `test_a_capped_record_rendered_without_its_listing_says_its_rows_in_scope_may_be_missing`, `test_the_slice_body_is_bounded_in_bytes_and_says_what_the_bound_cut` |
| **P01-24** owner-qualified changed-input reconciliation | **Met.** A map holds no mutable governing fact (no WIS, CNI, AEV or ADC fact) and calls nothing CURRENT on a timer; the slice tells its reader to re-establish any consequential claim against the source, and a Lead's dispatch reconciles a STALE map against the work's base before the pack is built | `test_no_map_freshness_turns_current_on_a_timer`, `test_a_lead_dispatch_at_a_stale_head_refreshes_and_selects_the_heads_map_once` |
| **P01-29** no ambient unbounded graph | **Partly.** A pack carries the bounded slice, never the record, a graph or history; the Lead's results carry its byte count, not its body. The wider path is direct source reading in the worker's own workspace (its cost is the worker's reads), and `aew map show --section` or `aew map diff` for the Lead and the operator (bounded by the record's caps; failures are typed errors). A typed, cost-bounded map read for workers is F15.8's (HOLD-06) | `test_the_slice_is_bounded_never_the_whole_record`, `test_the_leads_results_carry_the_slices_bytes_and_never_its_body` |
| **P01-32** no autonomous scope or instruction effects | **Met.** Making, selecting or reading a map changes no dispatch, gate, transition, control revision or resume; an invocation's credential cannot make or select one; repository text in a map stays escaped, fenced data | `test_no_map_state_changes_dispatch_gates_transitions_or_resume`, `test_map_commands_change_nothing_outside_local_maps_and_never_the_control_revision`, `test_an_invocation_credential_is_refused_map_generate`, `test_prompt_like_fence_breaking_and_escape_names_stay_inert_data` |
| **P01-34** profiles and graceful degradation | **Met** by this page and the absent-map behaviour above | as above |
| **P01-37** evidence class from observed production | **Met.** Every map a reader serves (the slice's first line, the resume row, `aew map show` and `generate`) is labelled `AGENT_REACHABLE_DERIVED` (`aew.maps.EVIDENCE_CLASS`); the artifact never carries a class, and no code path assigns another. At-use recomputation (`aew map diff --commit`, the regenerated pack's rebuild from the pinned commit) is available but runs as the same agent-reachable code, so it upgrades nothing | `test_every_map_read_is_labelled_agent_reachable_derived_and_selection_never_upgrades_it` |
| **P01-38** shared derived publication and selection | **Met as "no shared qualified selection".** The Lead's selection is a compare-and-set on the local registry's own revision, attributed in its log, and never a shared qualified selection; local maps and at-use recomputation stay available; selection changes no class and no authority | `test_selection_is_a_compare_and_set_on_epoch_and_revision_in_its_own_domain`, `test_every_map_read_is_labelled_agent_reachable_derived_and_selection_never_upgrades_it` |

The tests are in `tests/unit/test_map_slices.py`, `tests/unit/test_structural_map.py`, `tests/unit/test_map_store.py`,
`tests/integration/test_maps_v01_profile.py`, `tests/integration/test_map_context.py`,
`tests/integration/test_map_refresh_at_use.py`, `tests/integration/test_structural_map_git.py` and
`tests/integration/test_map_init.py`.
