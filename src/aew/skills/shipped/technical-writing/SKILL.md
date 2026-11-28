---
name: technical-writing
description: Write or revise technical explanations, guides, reference material, requirements, contracts, ADRs, implementation notes, and engineering records for a specific reader. Preserve source authority, normative meaning, and evidence qualifications. Skip pure code edits, exact transcription, and routine acknowledgements.
metadata:
  version: '0.2.1'
  status: candidate
---

# Technical writing

## Purpose

Help the reader understand, decide or act without reconstructing the writer's investigation. Use enough explanation for the task, with no loss of meaning to achieve brevity.

## Task archetypes and target workers

For technical conversations, documentation, operational messages and engineering records. Helps writers that bury the answer, compress complex ideas into jargon, repeat history, or turn qualified evidence into broad claims.

## Use and non-use

Use for substantive explanations or text someone will act on. Keep a review-only assignment read-only. Skip pure code changes, literal copying and routine short replies. Honor the requested language, depth and house style; do not impose a prose rewrite on creative work or exact quotations.

## Inputs and outputs

Inputs: reader, question/task, intended medium, relevant source material and required format. Infer the reader from context before asking. Output the requested text, with necessary evidence or limits close to the claims they qualify. Keep drafting notes and stylistic self-assessment out of the deliverable unless requested.

## Preconditions

Use this procedure within the assignment's scope and permissions; it grants no additional authority. Distinguish adopted requirements, proposed decisions, implemented behavior and verified observations; establish each source's status and authority. A recommendation, document title, code path or test snapshot does not by itself create a binding obligation. Preserve normative keywords, identifiers and governing quotations when their exact wording matters.

## Procedure and decision points

1. **Set the reader's task.** Privately name what the reader needs to understand or do and what they already know. Lead with the answer, outcome or decision, then the explanation needed to use it. Avoid making the reader traverse the system's architecture or the conversation's history first.
2. **Match the form to the need.** Explain causes for understanding; give ordered actions for a procedure; organize reference facts for lookup. Identify whether the artifact establishes requirements, explains decisions, describes implementation or reports verification; preserve those distinctions. Combine forms only when useful, with a clear transition. For difficult concepts, read [explanations](references/explanations.md). For operational guides or reference material, read [guides and reference](references/guides-and-reference.md). For errors, refusals, PRs or decision records, read [messages and records](references/messages-and-records.md). For normative requirements or interface contracts, read [specifications and contracts](references/specifications-and-contracts.md).
3. **Anchor the claims.** Trace consequential values and behavior to their owner. Identify a number as a decision, dated measurement with conditions, or snapshot. Derive repeated inventories from the owner where feasible; otherwise link or check the copy against it. Quote governing decisions/fix lines exactly with a locator when carrying their authority forward; label your interpretation separately. A summary for another audience must preserve qualifiers, permissions and exceptions.
4. **Build a connected explanation.** Give each paragraph one main point; let following sentences explain its cause, consequence or example. Name the actor and use concrete verbs. Keep related conditions beside their outcomes. Define unfamiliar terms at first use, preserve established technical terms when they are precise, and keep names consistent. Use a small example when abstraction leaves the mechanism unclear. Do not invent certainty or a simpler mechanism to make the story smoother.
5. **Remove friction, not substance.** Cut throat-clearing, praise, empty emphasis, repeated summaries and history that does not change the reader's action. Replace invented labels and dense noun strings with a direct explanation. Split overloaded sentences, but keep causal connections; do not turn prose into disconnected fragments. Use lists for real steps or parallel items, tables for comparisons, and headings for useful navigation. Avoid a heading for every sentence, decorative bold and nested lists that obscure the point. No universal word or sentence quota overrides clarity.
6. **Preserve scope and uncertainty.** Make the claim as narrow as the mechanism/evidence. Keep material limits next to the claim. State established facts directly; explain specific unknowns and their effect instead of hedging every sentence. Spell out ambiguous notation, units and boundaries. Distinguish an actual line break from literal backslash-plus-n, or show the relevant bytes when necessary.
7. **Check the reader's path and the final artifact.** Verify consequential commands, paths, links and locators against the intended revision/environment. Execute operational examples only where authorized and safe; use isolated fixtures when suitable and label checks not run. Read back saved text and inspect the rendered form when the tool or medium can alter it. Compare the final wording against its source again, especially after shortening. Stop when the reader can answer the question or perform the task and remaining evidence gaps are explicit.

## Verification and evidence

Separate source inspection, executed instructions and reader testing. For a guide, follow the steps in a clean supported environment when available; do not claim a cold-reader test from your own familiarity. Ask whether the text preserves every consequential condition and gives an available next action. Readability scores and word counts can flag friction, but do not prove comprehension or correctness.

## Failure modes and common mistakes

- A concise rewrite drops “required,” “only after retries,” or a permitted exception.
- An operator message exposes internal codes while omitting the action the operator can take.
- A title claims complete protection when the change addresses one specific failure mode.
- A shorter paragraph removes the example needed to understand a difficult concept.
- An invented command, recovery step or policy makes the prose sound complete.

## Abstention and escalation

If an essential source or behavior is unavailable, write the supported portion and name the smallest missing fact. Do not fabricate instructions or silently settle a conflicting rule. Missing execution access limits verification, not all useful writing.

## Examples

Synthetic good: “The reader reports the file absent only after all retries fail. A temporary miss during replacement can therefore recover.” Synthetic bad: “Missing files return absent.” The shorter version removes the condition that defines the behavior.
