# Messages and engineering records

Read for errors, refusals, status updates, PR descriptions, decisions or change notes.

**Errors and refusals:** say what failed or was refused, the supported reason, and an action this reader can actually take. Do not blame the reader for service failures or prescribe a retry when it cannot help. If no user remedy exists, state the available escalation or limitation honestly. Use visible control names for operators. Keep internal identifiers in appropriate diagnostic detail when they help support, rather than banning useful identifiers everywhere. Preserve required machine-readable fields and error codes.

**Updates and PRs:** lead with the problem and resulting behavior. Include why the change matters and the relevant validation/limits. Match title scope to the implemented mechanism. Say whether evidence came from local checks, CI or inspection; a code-review judgment does not imply CI passed. Use the host's required revision/run identity fields. Avoid a chronological account of abandoned attempts unless it explains a tradeoff the reader must assess.

**Decisions and briefs:** retain exact consequential wording and its source. Label interpretation or a proposed class-wide extension. Preserve “required,” timing clauses, exceptions and the difference between may/must. Trace numbers to a decision, measurement or snapshot. If decisions conflict without clear supersession, surface the conflict rather than quietly choosing one. A summary does not become a new policy owner.

**Review after saving:** read back the actual text. Check rendered links, references, escaped characters and qualifiers if the editor/template can transform them. Report what the saved artifact contains, not what was sent to the editor. Keep uncertainty specific: “Linux tests passed; Windows checks were not run” is more useful than a blanket “this should probably work.” Do not add a new disclaimer section when one precise sentence is enough.
