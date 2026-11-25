**Built (`fix/e183-steering-text`), the row's whole Work:**

- **The catalog item.** `contract.STEERING_ARGUMENTS` is the steering tool's one owner: the advertised action enum
  (`lower`, `request_raise`) and the schema's properties are derived from it, and the runner checks a call against it.
  `request_confirmation` and the `action_ref` only it took are gone from the enum and the schema, so a call naming it is
  an input error; `request_raise` stays advertised. The engine's own confirmation request (`steering_request` with kind
  `confirmation`) is unchanged, so a request recorded before this change still reads and notifies.
- **The text, as a run receives it.** The tool's standard and compact descriptions, the Lead's system text (a
  `Steering:` line, from `contract.STEERING_STEP`, the owner the tool's text also uses) and the Lead's refusal of
  `aew lead mode raise` say what works: a lower needs the operator's raise first, a project with no `steering.mode`
  refuses every action, and in crawl and walk the Lead takes each step itself. The `aew g3 request` refusal (the custody
  refusal) and `cli/g3_commands.py` no longer point the Lead at `request_confirmation`.
- **The crawl and walk stop** keeps `CONFIRMATION_UNAVAILABLE`, names the step as the Lead's ("`ticket_start` on T-1 is
  your step: ...; take it yourself with the `ticket_start` tool"), and is a quiet stop, never spooled or notified.
  `HELD_UNTIL_E7C` is renamed `LEADS_OWN_STEP`: the stop is still kept from the Lead's `loop_waiting` wake, as the
  operator's ruling on the quick check of E228's fourth PR (QC-1 (c)) had it, since the row does not lift that.
- **Comments that promised E7c, E6b or E8b** now say what is built (the endpoint, the broker's operator list, custody's
  PIC publish, the anomaly docstring, the execution template's steering comment, which moves the init policy digest).
- **The notify-event enum** loses `confirmation_pending` and E7d's `envelope_ended`, `published_under_pic` and
  `pic_not_exercised`, which nothing emits.
- **Tests:** `test_the_steering_tool_never_offers_request_confirmation_and_request_raise_stays_offered` and
  `test_the_steering_text_says_what_works_as_a_run_receives_it` (`tests/unit/test_surface_contract.py`),
  `test_a_crawl_stop_names_the_step_as_the_leads_and_is_quiet_never_notified_nor_woken`
  (`tests/integration/test_steering_loop.py`); the pinned catalog digests in `tests/integration/test_message_send.py`
  and the Lead projection goldens. The surface map's `steering` entry notes the two actions it offers.
- **Not closed here:** SYS-04's `remaining` still names E183, so closing the row would be a `stale_slice` problem in
  `tools/systems.py`; the close goes with the SYS-04 update.
