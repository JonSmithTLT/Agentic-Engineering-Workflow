---
version: alpha
colors:
  canvas: "#f5f7fa"
  surface: "#ffffff"
  text: "#1f2937"
  muted: "#596779"
  border: "#d7dee8"
  accent: "#315bcb"
typography:
  sans:
    fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"
    fontSize: "14px"
    lineHeight: "1.5"
  utility:
    fontFamily: "monospace"
omitted:
  - section: spacing
    reason: "Existing shared CSS owns spacing; W03 introduces no independent scale."
  - section: rounded
    reason: "Existing shared CSS owns shape values; no redesign."
---

## Overview

AEW is a read-only engineering workbench for an operator inspecting supplied workflow and evidence. This reconciles `docs/design-direction.md` with the W03 approved density choices; it is not a rebrand. English UI, source timestamps labeled UTC, system theme default. No remote fonts/assets or decorative animation.

## Colors

`src/styles.css` is the canonical runtime owner; frontmatter documents its light tokens. Dark canvas/surface/text/muted/border/accent: #161b22/#202832/#e5eaf1/#a9b5c5/#354253/#9bb8ff. Shared CSS custom properties feed all screens. Type accents never indicate truth; supplied semantic labels remain text. Forced colors remain operable.

## Typography

System sans body14px, main heading26px, section headings15px; raw IDs/code use monospace. Long source IDs wrap, tables scroll within their panel.

## Layout

Preserve existing responsive navigation and natural document scrolling. W03 has a stream and one selected-record inspector; below1024px show Stream/Detail controls. Inspector Summary/Evidence/Provenance tabs show one activity at a time. Graphs/metadata are disclosed within provenance. Fifty-entry pages; no accumulation. Do not apply viewport locks to shared ancestors.

## Elevation & Depth

Existing panels use restrained borders and no new ornamental shadows. Journal adds no modal layer or permanent third pane.

## Shapes

Inherit shared buttons/selects/panels. Native selects own their popup geometry; verify open popups and keyboard operation.

## Components

`InvestigationWorkspace` owns selection layout/mobile switching/close. `RelationsExplorer` owns explicit bounded exploration. `SourceStrip` owns source versus browser metadata. `SafeContent` owns hostile Markdown rendering. `Pager` owns cursor navigation. Canonical behavior is in `UX-CONTRACT.md`.

## Do's and Don'ts

Preserve provenance authority, visible unknowns and source roles. Avoid repeated metadata or additional controls for unavailable backend capabilities. Journal fixture/provisional modules must never enter production.

Journal type identity combines the existing muted/accent colors with distinct edge patterns and a small symbol. The disclosed type legend explains the same symbols and patterns; none indicates truth or applicability. Mobile pane controls show their pressed state and selected ID. Following a Journal reference focuses the new detail heading below the shared sticky header. Graph source controls form spaced, wrapping rows rather than a stack of touching buttons.

Desktop list selection keeps focus and document position in the results. A polite selected-ID status communicates the selection; heading focus is reserved for replacing phone detail and navigation from within detail or a deep link.

W04 uses paired source headers and a structural field comparison, with A/B stacked within each field below1024px. Packet inspection replaces comparison rather than adding a third pane. Source headers and packet cards inherit shared16px panel spacing. The restrained signature is paired source identity, not decorative outcome colors. Packet Contents/Selection & budget/Receipts/Provenance display one active activity. References show IDs once; supplied Journal references use the existing Journal route, while unsupported primitives remain explicit references.
