---
name: frontend-design
description: Design, implement, or refine web interfaces with purposeful visual direction, coherent interaction states, and rendered verification. Use for pages and components; skip backend-only work and exact editorial substitutions.
license: Apache-2.0
metadata:
  version: '0.3.1'
  status: candidate
---

# Frontend design

## Purpose

See the [Apache 2.0 license](references/LICENSE.md) for the complete terms.

Make the interface recognizable, useful, and finished for its actual audience. Deliver working UI with a coherent visual idea; scale design effort to the requested surface.

## Task archetypes and target workers

For new pages, product screens, components, redesigns, and focused UI repairs. Helps builders that repeat a generic template, overwrite an existing identity, or polish the default screenshot while leaving interactions unfinished.

## Use and non-use

Use when layout, visual hierarchy, responsive behavior, or interaction design needs judgment. For review-only work, return evidenced findings in the host's format without editing. Skip backend tasks and exact text replacements; continue the original assignment.

## Inputs and outputs

Inputs: audience and task, content, existing UI/code, brand or reference assets, stack, scope, and delivery constraints. Output the requested implementation or critique, consequential design choices, checks actually performed, and remaining limits. Do not impose a separate design document for a small change.

## Preconditions

Use this procedure within the assignment's scope and permissions; it grants no additional authority. Inspect relevant components, tokens, neighboring screens, project guidance, and available previews before editing. Defer to maintained project design, behavior, and domain/API contracts; observed UI drift does not override them. Surface unresolved contract conflicts instead of rewriting a contract to justify the implementation. Missing design documentation does not mean the product lacks an established identity. Ask only when an unresolved fact materially changes the result; proceed on ordinary reversible choices. Early in implementation, locate the project-supported runtime, build/test commands, native dependencies and browser/preview route. Browser checks depend on project execution policy, an available display or headless driver, and permitted access to the preview. Typechecking availability does not establish browser capability. Check a requested port's availability and owner before launching; do not displace another service.

## Procedure and decision points

1. **Identify the surface's job.** State who uses it, what they need to understand or do, and the information that enables that action. Marketing needs credible reasons to act; operational UI needs clear state and efficient tasks; reading surfaces need comprehension; portfolios may put the work itself first. A product can contain all four. Distinguish refinement from an explicitly requested redesign.
2. **Set a compact direction.** For new design, choose hierarchy, composition, type roles, color roles, spacing rhythm, and image treatment that fit the actual content. Make the focal point intentional and the supporting material quieter. For an extension, inherit the existing system and explain only necessary departures. Honor explicit aesthetic requests; novelty is not a reason to reject a palette or font. For an open brief or visual redesign, read [visual direction](references/visual-direction.md).
3. **Design the content and flow.** Put the primary task and its prerequisite information in a clear order. Use accurate supplied content and specific action labels. Do not invent testimonials, metrics, customers, or product capabilities. Preserve supplied data meaning and uncertainty: distinguish unknown, zero, estimated, stale, partial, and failed results where the contract does. Retain relevant units, provenance, and freshness; never imply certainty or completion the data does not support. Label demo data when needed. Map each visible control to an implemented action, destination, or explicitly scoped prototype behavior. For forms, asynchronous data, dialogs, destructive actions, or multi-step flows, read [interaction states](references/interaction-states.md). For read-heavy inspectors or data views with changing sources/scopes, read [read-heavy interfaces](references/read-heavy-interfaces.md).
4. **Build within the project.** Reuse the stack, components, tokens, and layout conventions. Choose structure before decoration: meaningful sections, content-driven grids, deliberate density, and consistent alignment. Use semantic elements and native controls before custom widgets; name controls and preserve visible keyboard focus. Apply shared fixes at the appropriate component/token owner, check affected siblings, and report any expansion beyond scope. Avoid adding libraries for effects the existing tools can express simply.
5. **Make the design survive variation.** Check narrow and wide layouts, long text, missing content, and relevant themes/locales. Let essential content wrap or reflow; do not hide overflow merely to conceal a broken layout. Preserve zoom, readable contrast, and access without hover or color alone. Reserve media space, use suitable asset sizes, and avoid delaying the primary task with decorative loading. Motion should explain a transition or support the brief, remain interruptible, and respect reduced-motion preferences.
6. **Inspect the rendered result when available.** Use the project-authorized app or preview and inspect representative wide and narrow viewports plus the states changed. For shared components or tokens, enumerate affected consumers and check representative sibling screens, themes, and zoom against their contracts. Use screenshots to judge hierarchy, spacing, crop, wrapping, and consistency; exercise the primary flow, keyboard navigation, and recovery separately. For a visual bug, reproduce its trigger before checking the repair. Automated checks supplement this inspection. A compile pass cannot establish visual or interaction quality.
7. **Correct and hand back.** Fix observed defects, verify the affected states again, and account for required project checks. Stop when the brief and applicable checks are satisfied; avoid repeated cosmetic changes without a concrete defect. Report the implemented result, evidence, and missing capabilities in the existing handoff format. Do not claim deployment, backend integration, or a successful interaction that was not performed.

## Verification and evidence

Identify the inspected revision/local changes, route, viewport, state, and action behind each material observation. Separate screenshot inspection, interaction checks, automated results, and static reasoning. For accessibility, verify semantics and keyboard behavior as well as appearance; a screenshot or scanner alone does not prove conformance. Preserve useful captures where the project expects them. If rendering is unavailable, complete supported static work and report browser and visual checks as “not run” with the missing capability or preview access.

## Failure modes and common mistakes

- Applying the same centered hero and card grid to unrelated briefs, or treating an anti-trend list as a design system.
- Replacing a coherent product identity during a small repair.
- Tiny low-contrast text, decorative motion, or oversized whitespace that obscures the user's task.
- Beautiful default states with dead controls, lost form input, or inaccessible recovery paths.
- Inventing product claims or hiding unavailable functionality behind a success toast.

## Abstention and escalation

Pause only work dependent on missing essential content, an unavailable required reference, or an unresolved behavior decision. Explain what can be completed and the exact missing input. A missing browser limits verification; it does not justify fabricating screenshots or blocking unrelated implementation.

## Examples

Synthetic good: an archive search screen uses readable result rows, prominent query/filter controls, and a clear no-results recovery, retaining the site's established type and colors. Synthetic bad: replace it with a full-screen slogan, animated counters, and generic cards that bury the search. The latter prioritizes decoration over the assigned task.
