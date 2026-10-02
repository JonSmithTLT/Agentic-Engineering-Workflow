# D1 Overview and Ticket visual review

Status: **PENDING designer/user review**. C0 0.1.2 is accepted; D1 implementation and focused validation pass. This packet satisfies the concrete review prerequisite in the approved plan: “Review a running mock Overview and realistic Ticket detail before expanding the remaining pages.”

## Running compiled previews

- [Overview](http://127.0.0.1:4173/?fixture=F1)
- [Ticket detail](http://127.0.0.1:4173/work/T-0001?fixture=F1)
- [Work hierarchy](http://127.0.0.1:4173/work?fixture=F1&view=tree)
- [Large bounded Work page](http://127.0.0.1:4173/work?fixture=F6)

The theme selector supports System (default), Light and Dark. Demo data is visibly identified. These local servers do not require a VS Code restart. To recreate them, build demo and run `npm run preview:demo` from web/ with the documented cached environment.

## Static review artifacts

- [Overview light](screenshots/d1/overview-light.png), [Overview dark](screenshots/d1/overview-dark.png), [Overview phone](screenshots/d1/overview-phone.png)
- [Ticket dark](screenshots/d1/ticket-dark.png)
- [Work tree](screenshots/d1/work-tree.png), [large page](screenshots/d1/work-large-page.png), [Work phone](screenshots/d1/work-phone.png)

Review the operator summary and attention hierarchy, Ticket intent/reasons versus inspection facts, compact spacing/readability, and theme/responsive behavior. Tree scope is honestly page-limited; all-loaded-rows mode supports keyboard inspection. Backend state, reasons and counts retain their meaning; navigation into later-stage views explains the pending stage or unavailable capability.

Validation: 51 offline tests and 18 compiled browser checks pass; see `validation-d1.md`. Production uses the same domain components without fixture code. Live integration, D2–D4 and independent core frontend review are not yet accepted.

Decision to record here after actual review: accepted visual direction, or specific changes required before expanding the remaining pages. No visual approval is inferred from passing tests.
