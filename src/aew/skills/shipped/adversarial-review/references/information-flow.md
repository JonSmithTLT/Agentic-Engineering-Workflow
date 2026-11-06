# Information-flow and projection review

Read for redaction, filtering, sanitization, projection, or claims that protection is unchanged or never weaker. State the actual guarantee: which information must be withheld, from which audiences/channels, under which encodings and size limits.

Map input through decoding, normalization, filtering, formatting, truncation, and final output. Include errors, diagnostics, metadata, and fallback channels within the contract. An earlier filter is insufficient if a later renderer reconstructs the value or a failure path emits the original input.

For "never narrows" or "unchanged" claims, define the semantic comparison first. Freeze the baseline implementation and dependencies, then compare identical seeded inputs against the new subject. A redaction monotonicity check asks whether previously withheld information is now observable, not merely whether outputs are byte-identical. Preserve valid public-output controls to catch excessive filtering as well.

Build a bounded hostile corpus from the input domain: nested containers, bytes and decoded strings, escaped or split representations, resolved constants, alternate encodings, malformed/truncated values, and boundary sizes. Do not execute arbitrary code to decode literals. Test relevant channels and the final serialized bytes, including multibyte text near byte limits. A character count may not enforce a byte bound.

Make the corpus and baseline identity reproducible. Keep minimal witnesses and actual outputs. A finite differential finds counterexamples; it does not prove every possible input safe. Enumerate covered forms and blind spots, and use targeted ablations to establish which protection each regression observes.

Synthetic witness: the input filter withholds a value in a string field, but an error formatter includes its raw bytes. A check of the success response alone misses the second channel. The contract determines whether the error channel is prohibited; do not invent that obligation after seeing the output.
