# T5 probe: a Git-object-based codebase map is cheap and reproducible, with two corrections to the design note

- **Status:** probed fact for `T5-project-maps.md` §2–§3 (the codebase map record and its freshness), 2026-10-04, after the designer asked for "a small prototype to validate that Git-object-based generation is as cheap/reproducible as we expect" once the D9 spike was done. Probe: `repro/t5/codebase_map_probe.py`; outputs `repro/t5/probe.*.out.txt`; two generated records `repro/t5/codebase-map.*.yaml`. Read-only against three repositories; nothing written into any of them. The designer's edited `docs/T5-project-maps-v0.3.md` (untracked in the live checkout) was not read; the probe implements §2 of this review's note.
- **Answer.** Yes. Generating every §2 section from Git objects alone takes about 0.1 s without the Python import graph and 0.6–0.75 s with it on the AEW repository (798–930 tracked files, 212–217 Python modules); the record is 3.5 KB without the graph and 28 KB with it; the same commit generated from two different checkouts on different branches gives byte-identical records; three repeats give the same digest every time. Two corrections to the note came out of it (§3): the generator must read the **commit's tree** (`ls-tree`), not the index (`ls-files`), and the freshness rule can be far quieter than "STALE on any commit".

## 1. Method [documented fact: the probe's design]

The probe builds the `aew/codebase-map/v1` record exactly as `T5-project-maps.md` §2 lists it, from Git objects only: `git ls-tree -r --name-only --full-tree <commit>` for the file listing, `git show <commit>:<path>` for the two or three configuration files the sections read (`pyproject.toml`, `package.json`, `.gitattributes`), and one `git cat-file --batch` for every `.py` blob when the import graph is on. It never opens the working tree. It times each section, dumps canonical YAML (sorted keys), prints its SHA-256, and repeats three times. `ignored_but_present` is recorded as `null` with a note, because it needs the working tree (§3).

Targets: this review's frozen `tree/` at `dcd43f1`; the live `Agentic-Engineering-Workflow` checkout (on `impl/m4-b-containment`) at the same commit `dcd43f1` and at its own head `56b85ad`; the public `security-platform-toolchain` at `3bf796b`.

## 2. Numbers [probed fact]

| Target | Tracked files | Python modules / intra-repo edges | Record | Total per run | of which `imports` |
|---|---|---|---|---|---|
| `tree` @ dcd43f1 | 798 | 212 / 578 | 27,926 B, 1,134 lines | 0.75 s | 0.63 s |
| live repo @ dcd43f1 (other checkout, other branch) | 798 | 212 / 578 | **27,926 B, byte-identical** (`cmp`) | 0.60 s | 0.49 s |
| live repo @ 56b85ad | 930 | 217 / 601 | 28,694 B | 0.61 s | 0.52 s |
| `tree` @ dcd43f1, no imports | 798 | — | **3,532 B, 196 lines** | **0.11 s** | — |
| security-platform-toolchain @ 3bf796b | 330 | 32 / 0 | 6,762 B | 0.15 s | 0.07 s |

Every run was deterministic across its three repeats (identical SHA-256). Section costs without imports are a handful of `git` invocations at about 20 ms each on Windows (`ls-tree`, three `show`s); the pure-Python work (directories, languages, roles) is under 10 ms. The import graph is one `cat-file --batch` of every `.py` blob plus `ast.parse` of each; it is the only part that grows with code size, as the note said, and it is 85–90% of the time and of the bytes.

What the probe read per map: the listing plus 2 files (no imports) or plus every `.py` file (imports). That set is the record's `observed_paths`.

## 3. Two corrections to `T5-project-maps.md` [probed fact, then inference]

1. **`git ls-files` is not commit-bound.** The note's §2 says `directories` comes from `git ls-files`. The first run used it and produced *different* records for the same commit in the two checkouts: 809 files in `tree/` (its index is `docs/restructure` = dcd43f1) and 930 in the live checkout (its index is `impl/m4-b-containment`), with 220 versus 217 Python modules (`repro/t5/probe.*.ls-files-first-run.out.txt`). `ls-files` lists the index of the checkout, not the tree of the commit the map claims to describe. With `git ls-tree -r --name-only --full-tree <commit>` the two checkouts agree byte for byte. **[rec]** §2's `directories` source becomes `ls-tree` at `source_revision`; a test asserts the map of a commit does not depend on the branch checked out. This also means the map can be generated for the authoritative commit while a role's workspace is checked out elsewhere, which `aew map generate --commit H` needs.
2. **Freshness can be section-scoped, not "any commit".** §3 says a map whose `observed_paths` is the whole tracked tree goes STALE on any commit. But the map does not depend on every file's *content*: without imports it depends on the **listing** (names, which change only when a path is added, deleted or renamed) and on the contents of two or three configuration files. Measured on the live repository: of the 247 paths that changed between dcd43f1 and 56b85ad, 174 were adds/deletes/renames and 73 content-only modifications; of the last 30 commits on `origin/main`, 9 changed the listing and 21 changed contents only. So a listing-plus-config freshness rule would have kept the map CURRENT through 21 of 30 recent commits, instead of 0 of 30; with the import graph on, a modified `.py` also stales it (40 of the 73 modified files were `.py`). **[rec]** `observed_paths` for the no-imports map = the configuration files read, plus a new marker the freshness code understands: "the tree listing" (STALE when `git diff --name-status --diff-filter=ADR <observed> <authoritative>` is non-empty). With imports, add every `.py` path, which is the current rule for those files. Either way, regeneration costs a tenth of a second, so the only thing at stake is how often a pack says STALE.

Also observed: `ignored_but_present` (which `.gitignore` patterns match existing directories) cannot be computed from objects; it is a statement about a particular working tree. **[rec]** drop it from the commit-bound record, or compute it at pack time for the role's workspace and label it as such.

## 4. What this settles for the designer's questions in `T5-project-maps.md`

- **Q1 (generate at `aew init`):** at 0.1 s with no code execution and no working-tree reads, yes; and because the map is commit-bound, `init` can generate it for the authoritative head whatever is checked out.
- **Q2 (import graph in v1):** it is the whole cost (6× the time, 8× the bytes). The data says ship v1 without it or behind a flag, and let the K-arm evaluation decide whether a 25 KB module graph earns its place in a pack; the probe shows it can be added later without touching the rest of the generator.
- **Q3 (STALE blocks nothing):** unchanged; the section-scoped rule above only makes STALE rarer and therefore more meaningful when it appears.

## 5. Not shown [hypothesis]

- Repositories an order of magnitude larger (10k+ files): `ls-tree` and the directory pass are linear and fast, but the import graph's `cat-file --batch` of every Python blob is the part to watch; the §2 cap at 500 modules bounds the record, not the time.
- Languages other than Python for the graph.
- **The fixed role table is the weak section** [probed fact]: on AEW it labels 2 of 7 top-level directories `unknown` (`eval`, `web`); on the SPT repository 8 of 13 (`common`, `data-bundles`, `examples`, `images`, `offline-bundles`, `queries`, `requirements`, `rules`). That is the honest output of a rule table that never guesses, and it is what KC §8.3 asks for (derived facts, not inferred purpose), but it means the codebase map alone will not tell a role what `rules/` or `queries/` are; that is the architecture map's job (`T5-project-maps.md` §6). A wider table (`examples`, `images`, `data`, `assets`, `requirements` → `data`/`examples`/`config`) would cut the unknowns on these two repositories, at the cost of more rules to argue about.
