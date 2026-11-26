# Explaining difficult ideas

Read when the reader needs a mental model or a causal explanation, not just an instruction.

Start with the question the explanation answers. Give the result in familiar terms, then introduce only the concepts needed to explain why. Establish prerequisites before relying on them. A technical reader may need precise terminology rather than elementary background; a newcomer may need the same term defined through an example.

Use a causal sequence: initial situation, change, consequence. Carry one concrete example through it instead of switching examples for every sentence. When order matters, show the sequence or a small diagram. Define symbols and units next to their first use. Keep formulas and implementation detail only when they help the reader reason or reproduce a result.

For example, explain a stale response by following an old search request and a newer one through completion. Then name the protection: only results for the current request may update the view. Do not replace the mechanism with “race-safe orchestration,” or imply cancellation always stops a remote source.

Layer detail. The opening should answer the question; later paragraphs can explain the mechanism and its limits. A concise answer can still need several paragraphs for a difficult topic. Do not hide a condition that changes the answer in an optional appendix. Use an analogy only if it reduces work for this reader; state its limit and return to the real mechanism. An analogy is not evidence.

Read the draft without relying on the original conversation. Can the reader tell what causes what, resolve pronouns, and understand why the example supports the conclusion? Remove repeated framing, unexplained abbreviations and sudden jumps. Ask a target reader to explain the distinction or apply it to a new case when conducting a comprehension test; “sounds clear” alone is weak evidence.
