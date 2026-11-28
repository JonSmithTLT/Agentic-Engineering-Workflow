I'd like one piece of work on the link policy extension (`markdown.extensions.linkpolicy`), which a comments site uses to render user comments safely. Plan it as one Story of separate pieces of work, show me the plan before anything changes, and run pieces that don't depend on each other in parallel where they can be.

1. Bug report (security): a comment containing `[click](JavaScript:steal)` or `[click](JAVASCRIPT:steal)` renders as a working link, although `javascript:` links are supposed to be neutralized. Lower-case `javascript:` links are neutralized correctly. A blocked scheme must be blocked whatever its letter case, and also when the URL starts with whitespace. Add a regression test.

2. Feature: add an option `rel_external`. Its default is `"nofollow noopener"`: every external link (an `http`, `https` or protocol-relative `//` link whose host is not one of the extension's `internal_hosts`) gets that value as its `rel` attribute. Setting it to an empty string turns this off. A host in `internal_hosts` also covers its `www.` form (`example.org` covers `www.example.org`). Internal, relative and blocked links never get it. It must work like the extension's other options (the constructor, `makeExtension` and `extension_configs`) and be documented with them.

3. Make `report()` and strict mode dependable. Applications reuse one `Markdown` instance for many documents and call `md.reset()` between them. All four must hold: (a) after `md.reset()`, `report()` is empty, and after converting a document it lists only that document's blocked links; (b) `report()` lists each blocked URL once, in the order in which the links first appear; (c) in strict mode, the `LinkPolicyError` that is raised names the blocked URL in its message and carries it as its `url` attribute; (d) the extension's documentation describes `report()` and how it behaves across `md.reset()`.

4. Bug report (security), after item 3: a comment containing `![logo](javascript:steal)` renders an image whose `src` is `javascript:steal`. Images must follow the same rules as links: a blocked image loses its `src`, keeps its `alt` text, is marked `data-link-policy="blocked"`, appears in `report()` like a blocked link, in the order it appears in the comment, and raises in strict mode. Images never get a `rel` attribute.

5. Users enable the included extensions by their short names (`extensions=['toc']`). Make `extensions=['linkpolicy']` and `extension_configs={'linkpolicy': {...}}` work the same way, both in this checkout and in a package built from it.

6. Branch review: a contributor sent the branch `contrib/allowed-schemes`, which adds an allow-list mode. Review it against `main` and tell me whether it is safe to merge, and why. Do not merge it and do not change it.

7. After the review in item 6: add an option `allowed_schemes`, done properly, so that a site can list the only schemes it allows. Fix whatever the review found. All of these must hold:
   a. Its default is `[]`, which means off. It works like the extension's other options and is in the documentation's option table.
   b. When it is not empty, only links whose scheme is in the list are kept. Schemes compare without regard to letter case.
   c. It takes the same kinds of value as `blocked_schemes`, and is checked the same way.
   d. Relative links still follow `allow_relative`, not the allow-list, but a protocol-relative link (`//host/path`) is checked as an `https` link.
   e. The links it neutralizes appear in `report()`.
   f. The documentation explains allow-list mode, and how it combines with `blocked_schemes`.

8. Documentation, last, once items 1 to 7 are done: add the extension to the documentation site's navigation (`mkdocs.yml`) and to the table of included extensions in `docs/extensions/index.md` (with its short name), and add an `Unreleased` section at the top of `docs/changelog.md` that lists every user-visible change from items 1 to 7.

Ground rules. Keep each change to the extension (`markdown/extensions/linkpolicy/`), its tests and its documentation, unless an item cannot be done that way: then tell me which other files it needs and why, before changing them. Add tests for every change of behaviour, and do not break any test that passes now (`python -m unittest discover -s tests -t .`). Items 1, 4 and 7 change what the policy lets through: I want each of them independently reviewed and verified. Item 8 is documentation only and needs no independent review or verification.
