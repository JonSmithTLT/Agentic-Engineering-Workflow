# Dashboard visual direction (D1)

The subject is AEW execution and evidence, for an operator keeping a browser beside the workflow. The first screen leads with the backend's short explanation and its reported health, followed by an asymmetric work/attention layout. Counts support those sections rather than forming a wall of statistic cards.

Use the approved six-color palette in light and dark themes: canvas #F5F7FA/#161B22, surface #FFFFFF/#202832, text #1F2937/#E5EAF1, muted #596779/#A9B5C5, border #D7DEE8/#354253 and accent #315BCB/#9BB8FF. Semantic warning and success colors distinguish transport messages; they do not infer domain outcomes.

System sans serif carries interface text (14px body, 26px page title, 15px section title). Monospace is reserved for raw identifiers and code. Tables have 36px rows. Content is left-aligned, with short explanations and bounded panels.

```text
navigation | project identity                          transport mode
           | heading                                   demo scenario
           | snapshot freshness
           | backend summary                           reported health
           | active work table                 | needs attention
           | active runs                       | recent activity
           | projection revision / generation / last check
```

Review against the brief: the header persists, navigation collapses below 1024px, tables scroll within their own panels, details stack on phones, and system appearance is the default. There are no remote assets or decorative animations. C0 is accepted. Overview and Work now share real API-driven components in production and demo; fixtures and demo controls remain excluded from production. Later domain pages await the specified visual gate.

D1 review compares the compiled mock Overview and a realistic Ticket detail, in both themes and at phone size. Domain expansion follows main-line C0 approval and visual preview feedback.

Compiled screenshot critique: the operator summary leads the Overview; work and attention have distinct widths and clear section boundaries. Dark and light palettes match the brief, and the 390px view keeps horizontal scrolling inside the work panel. The Ticket detail gives intent/reasons the main column and backend fields a narrow inspection column. No visual changes are required before the external preview review; domain expansion remains gated.
