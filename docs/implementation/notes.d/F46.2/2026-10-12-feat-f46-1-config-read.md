**Binding conditions from F46.1 (the F46.1 proposal §4.3, reviewed CLEAR; designer- and operator-approved).** F46.1
is a read-only projection: it supplies the configuration digest (`aew/config-digest/v2`,
`aew.engine.configuration.config_digest`), the document states, each field's `path`, `class`, `allowed` and `edit`,
and the per-document inventory (`aew settings show`). These are requirements on F46.2, not F46.1 designs: F46.2
designs and proves each one in its own proposal.

1. **The bind.** Save sends `expected_digest`. F46.2 recomputes `config_digest` (the same function) under the store
   lock and refuses on any difference, naming what changed (adopted, on-disk, or manifest), never a revision.
2. **It re-pins its own document only.** Once a pins map exists, a Save writes its document and sets
   `policy_sha256[rel]` for that `rel` alone: a per-document re-pin that F46.2 must add (`manifest_adopt` and
   `_read_policy_pins` re-pin every file). A Save never adopts another document's bytes: when the target shares its
   file with another manifest key, F46.2 refuses, naming both documents through the shared renderer (condition 3),
   and never re-pins a shared file on one document's behalf. Required F46.2 test: a Save to a document sharing its
   file with another key is refused, naming both.
3. **It refuses while anything else is drifted.** While the manifest or any other policy document is drifted, F46.2
   refuses with the registered code `OTHER_DOCUMENT_DRIFTED`. The refusal names the document as the inventory names
   it (its logical name when `documents[].document` shows it, otherwise "policy document `<index>` (name withheld)"),
   never a path or content, and its one-step fix, owned by the operator: "review `<document>`, then adopt it, or
   restore it", in that same form. One renderer serves the inventory, the refusal, its fix text and log lines. F46.1's
   inventory already shows the drift of every manifest policy document; from F46.2 on, `documents[].write.reasons`
   carries the code.
4. **Its states.** `write` becomes AVAILABLE for `ADOPTED`, and for `ABSENT` and `UNPINNED` under condition 5. It is
   UNAVAILABLE, with the reason, for `DRIFTED`, `INVALID` and `MANIFEST_DRIFTED`.
5. **No pins map: the first Save (requirements only).** A per-document re-pin on a project with no pins map would
   create a one-entry map, and every other policy file would then read as drifted, so the first Save establishes the
   whole map. The first Save may pin every policy file in one step when every file is provably unchanged (operator
   decision; no separate "adopt once first" step). How is F46.2's design.
   - **5a.** F46.2 never adopts content the operator has not been shown. Every file it pins is classified, the target
     included: the target's comparison base is its template plus the Save's own changes. A file with no template (the
     manifest's `pricing` entry, any further `policy` entry) is "no template". Templates are matched by logical name
     (the manifest key, or `execution` for the conventional path), never by path.
   - **5b.** Any file F46.2 cannot prove unchanged (it differs, has no template, or is invalid) takes the strict path:
     re-authentication at the operator's terminal, and from the dashboard a refusal naming the files and giving the
     terminal command. An invalid file is refused, named.
   - **5c.** "Unchanged" means parsed content, the basis of the legality digests (`policy_digests`), not bytes:
     comment-only, formatting and CRLF differences count as "equivalent to the init template (formatting or comments
     differ)", labelled so.
   - **5d.** Any diff F46.2 shows is, per entry, `{path, change: added | removed | changed}`, with a value only for a
     boolean, a number, a schema enum, or a string that passes a safe-name shape and the credential rule; an argv list
     or a path list as a count; a key failing the safe-key shape as the `@i` segment of the one path encoder
     (`aew.policy.config_paths`); at most 50 entries, then `truncated` and the total count.
   - **Tests F46.2 must carry:** an unpinned target with a hand-set `containment.mode: allow_weaker` plus an
     ordinary-field Save is strict; an unpinned project with a `pricing` entry is strict; a hand-edited `gates.yaml` is
     strict, and its dashboard Save is refused naming `gates`; an all-unchanged project's first Save is ordinary and
     pins every file; a CRLF or comment-only copy of a template is "equivalent"; an invalid file is refused, named; a
     hand-edited check command carrying a synthetic unprefixed token never appears in the preview; the template basis
     is one source (cross-checked against `INIT_POLICY_SHA256`); `OTHER_DOCUMENT_DRIFTED` names the drifted document;
     a drifted manifest policy key that is credential-shaped is refused as "policy document `<index>` (name withheld)",
     and the key appears in none of the CLI, dashboard or log output.
6. **First-Save approval binds to what was reviewed.** The approval of a first Save binds to the exact reviewed content
   and classification of every file being adopted. Any intervening change forces revalidation, and where it is
   material, renewed operator review.
7. **Strict adoption, and its route.** F46.2 keeps strict adoption for unproved content, but its review evaluates
   trusted F47.3 re-authentication and approval before locking exceptional adoption to terminal-only operation.
8. **Paths.** F46.2 and `aew settings set` take the canonical RFC 6901 pointer (`aew.policy.config_paths`), and refuse
   any path containing an `@` segment: a display-only, masked locator, valid only under the digest it was rendered
   with (`config_paths.is_identity`).
