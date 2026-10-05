# Work graph follow-up

Recorded 2026-10-02 from user visual feedback. Graph remains outside the approved D0–D4 core delivery and starts separately after core freeze. No implementation date is committed.

## User need

Large projects contain many epics, stories and tickets. A visual hierarchy and linkage view should help an operator identify where a ticket belongs, navigate related work and understand the surrounding project without losing context.

## Proposed location and behavior

Add Graph alongside Table and Tree inside Work, using the same filters and deep-linked detail routes. Start with backend-provided epic → story → ticket parent/child relationships. Keep other backend-provided relations distinct from hierarchy edges; do not infer relationships, workflow outcomes or dependencies from layout.

Start focused on a selected epic or story rather than drawing every record at once. Expand branches on demand, collapse completed branches using explicit filters, and provide pan/zoom, fit-to-selection and a small overview map if justified by visual review. Selecting a node should expose its ID, title, kind and backend state, with a link to its existing detail view. These are design proposals pending review, not changes to the accepted API contract.

## Data and accessibility prerequisites

The current bounded Work list is not a complete graph snapshot. A graph must identify loaded scope and truncated relationships explicitly. Backend contract review should establish bounded subtree traversal or a dedicated read projection, cursor behavior and revision coherence before implementation; never silently fetch all history or present a loaded page as the entire project.

Retain Table and Tree as keyboard-accessible alternatives. Graph navigation needs keyboard selection, visible focus, readable labels, theme support and an explicit treatment of historical records. Use local assets and validate the selected renderer under the proposed CSP; choose dependencies only when the feature consumes them.

## Review criteria for the optional phase

An operator can find a ticket's epic/story ancestry, expand a large branch without an unbounded request, follow a record to its detail page and distinguish hierarchy from other links. Incomplete scope is visible. Large-project browser checks establish responsiveness, bounded loading, keyboard access and revision behavior. Visual review assesses actual navigation benefit rather than decorative complexity.
