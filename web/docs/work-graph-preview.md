# Optional Work graph preview

Branch `feat/aew-dashboard-work-graph`, separate worktree `AEW-dashboard-graph`, based on accepted core/documentation `969b0bd`. Core implementation remains frozen at `7c120b4`. This optional feature has its own validation/review; it does not alter core acceptance or claim live integration.

Use the accepted bounded Work response as a graph **of the loaded page**. Parent arrows run left to right; actual record cards show backend ID, title, kind/state and historical status. Parents outside the page appear as dashed reference cards with no invented title/state. Focus a loaded branch, collapse/expand it, zoom, fit width and pan. A selected-record inspector gives context and an existing detail link. Preserve Table/Tree as accessible alternatives.

Design: the approved compact workbench palette/system fonts remain. Spend emphasis on the selected record and its incident parent edges; keep other connections restrained. Use native focusable buttons for cards and controls, locally rendered SVG paths for arrows, and CSSOM positioning compatible with the proposed CSP. No new dependency, remote asset, API capability or endpoint is needed.

The chart represents backend parent links only. It does not infer dependency, evidence, assurance, health or workflow relationships from nearby placement. Related records remain typed links in the inspector. It never fetches all history or follows every node into a new request. Full-project traversal, dependency overlays and broader search/metrics/comparison need separately reviewed backend projections.

Validation covers hierarchy layout and cycles, missing parents, focus/collapse, bounded large pages, unknown/historical states, deep links, keyboard controls, pan/zoom, both themes, phone panel overflow and the compiled CSP. Provisional preview review remains separate from the accepted core review.

User clarification retained: Attention's `Unknown value: WARNING` is an unregistered severity vocabulary, not malformed data. Main-line should declare severity labels in a reviewed contract/registry; until then, the frontend must not infer a severity mapping. A clearer unregistered-label explanation is a separate polish item, not a graph dependency.

Preview: `http://localhost:4187/work?view=graph&fixture=F1`. Select “Graph on this page” in Work. Validation and review boundaries: `validation-work-graph.md`. Implementer checks pass; optional review is pending.
