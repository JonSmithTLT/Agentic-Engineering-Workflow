#!/usr/bin/env python3
"""D2's rules (O-SECRET, O-CMD) and their ratchet: each ablation reverts one guard and names the test that must fail.

    python tests/unit/d2_rules_ablate.py CHECKOUT OUT.json [ID ...]

Every line runs on a throw-away copy, never on the checkout: `git archive` of the checkout's HEAD, one file mutated
(its text must occur exactly once), the named tests run with an absolute PYTHONPATH to the copy, `__pycache__`
cleared, and the file's bytes restored and checked by sha256. The clean copy must pass every named test first, or a
failure proves nothing. A line is killed when its tests fail. Exit status: 1 when any line is not killed.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

RULES = "tests/unit/test_discovery_rules.py"
CI = "tests/unit/test_ci_tools.py"
RATCHET = "tools/ci/discovery_ratchet.py"
ALLOWED = "tests/helpers/discovery/allowed.py"
PARSER = "tests/helpers/discovery/rules.py"
PASSES = "test_o_secret_passes_what_asks_for_nothing"
CATCHES = "test_o_secret_still_catches_every_ask"
NEXT = "test_an_ask_with_the_form_on_the_next_line_passes_and_each_near_miss_does_not"
OWN = "test_the_products_own_refusals_show_the_safe_path_and_read_as_no_ask"
FIELDS = "test_a_fields_line_parses_through_the_real_expansion"
NOBODY = "test_a_fields_line_with_no_body_shown_answers_for_its_command_only"
GATE = "test_d2_runs_on_every_pull_request_and_main_and_its_ratchet_in_the_gate_and_nightly"
NEG = "test_a_negator_that_governs_another_verb_does_not_excuse_the_ask"
GOV = "test_a_negator_still_governs_its_own_verb"
SEP = "test_a_separator_ends_a_prohibition_whose_verb_is_left_out"
PLAIN = "test_a_plain_negator_does_not_reach_a_new_verb"
SHOWN = "test_a_value_typed_where_it_shows_or_made_persistent_is_an_ask"
MASKED = "test_the_masked_and_clearing_forms_are_no_ask"
HANDOVER = "test_the_form_below_does_not_excuse_a_hand_over"
TWO = "test_the_form_written_over_two_lines_in_one_block_passes"
POSS = "test_a_possessive_of_something_other_than_the_value_is_no_ask"
VALUE = "test_a_possessive_that_is_the_value_still_asks"
PROMPT = "test_only_typing_or_entering_is_answered_by_a_prompt"
PUNCT = "test_any_punctuation_ends_a_prohibition"
CONNECT = "test_every_connector_ends_a_negation"

# id, what it reverts, file, old text, new text, test file, -k expression
LINES = [
    # O-SECRET: what asks
    ("S1", "the name's word boundaries gone", PARSER,
     r'r"(?<![\w-])(?P<what>{names})(?![\w-])")', r'r"(?P<what>{names})")', RULES, PASSES),
    ("S2", "the bare words' boundaries gone", PARSER,
     r'r"(?<![\w-])(?P<what>credentials?|tokens?)(?![\w-])"', r'r"(?P<what>credentials?|tokens?)"', RULES, PASSES),
    ("S3", "a bare word asks across a clause", PARSER,
     r"(?:(?!,|\b(?:then|but|which|when|if|of|{ASK_VERBS})\b)[^.;:\n])", r"(?:(?!\b(?:{ASK_VERBS})\b)[^.;:\n])", RULES,
     PASSES),
    ("S5", "a bare word as half of another noun asks", PARSER,
     r'rf"(?!\s+(?:{OTHER_NOUN})\b)"' + "\n", "\n", RULES, PASSES),
    ("S6", "the noun use of a verb asks", PARSER, 'if NOUN_USE.search(before) or OTHERS_ACT', 'if OTHERS_ACT', RULES,
     PASSES),
    ("S7", "another's act asks", PARSER, 'or OTHERS_ACT.search(before) or', 'or', RULES, PASSES),
    ("S8", "the farthest verb asks again", PARSER,
     r"(?P<between>(?:(?!\b(?:{ASK_VERBS})\b)[^.;\n]){{0,80}}?)", r"(?P<between>[^.;\n]{{0,80}}?)", RULES, CATCHES),
    ("S22", "the hidden prompt not honoured", PARSER,
     'return bool(HIDDEN_PROMPT.search(after) or (PLAIN_PROMPT.search(after) and NOTHING_ECHOED.search(after)))',
     'return False', RULES, PASSES),
    ("S23", "any prompt honoured", PARSER,
     '(PLAIN_PROMPT.search(after) and NOTHING_ECHOED.search(after))', 'PLAIN_PROMPT.search(after)', RULES, CATCHES),
    ("S21", "a prompt excuses a model", PARSER, 'if plane == MODEL or m.group(1).lower() not in PROMPT_ANSWERS:',
     'if m.group(1).lower() not in PROMPT_ANSWERS:', RULES, "test_a_prompt_is_no_way_out_for_a_model"),
    ("R24", "a prompt answers any verb", PARSER,
     'if plane == MODEL or m.group(1).lower() not in PROMPT_ANSWERS:', 'if plane == MODEL:', RULES, PROMPT),
    ("R22", "the reader's own will/would read as another's act", PARSER,
     r'r"(?<!you )\b(?:will|would)\s+$"', r'r"\b(?:will|would)\s+$"', RULES, CATCHES),
    ("R21", "a possessive of another noun reads as the bare word", PARSER,
     r'''rf"(?!['’]s?\s+(?:{OTHER_NOUN}|states?|status|formats?|expiry|age|scopes?|owners?)\b)",''', 'r"",', RULES,
     POSS),
    ("R23", "every possessive passes (main caught the value's)", PARSER,
     r'''(?!['’]s?\s+(?:{OTHER_NOUN}|''', r'''(?!['’]s?\s+(?:\w+|''', RULES, VALUE),
    ("R43", "a plain negator in the ask's own span negates what it does not govern", PARSER,
     'return not last.group("plain") or all(_filler(w) or w in DETERMINERS for w in _words(between[last.end():]))',
     'return True', RULES, CATCHES),
    ("R44", "a determiner ends a plain negator in the ask's own span", PARSER,
     'or w in DETERMINERS for w in', 'for w in', RULES, GOV),
    # O-SECRET: negation
    ("S9", "negation back to a 12-character window", PARSER,
     'not _negated(text, m.start()):\n            problems.append(f"asks to {m.group(1).lower()}',
     'not NEGATION.search(text[max(0, m.start() - 12):m.start()]):\n            problems.append(f"asks to '
     '{m.group(1).lower()}', RULES, f"{PASSES} or {GOV}"),
    ("S10", "don't not read as negation", PARSER,
     r"\b(?:ca|do|does|did|wo|must|should|may)n['’]t\b|", "", RULES, PASSES),
    ("S11", "refuse and ignore not read as negation", PARSER,
     r'r"|(?P<refuse>\b(?:refuse|ignore|disregard|reject|decline|avoid)\b)"', r'r"|(?P<refuse>\bzzzz\b)"', RULES,
     PASSES),
    ("S17", "negation looks past the sentence", PARSER,
     'start = max(max((m.end() for m in SENTENCE_END.finditer(text, max(0, at - 160), at)), default=0), at - 160)',
     'start = max(0, at - 160)', RULES, f"{CATCHES} or {NEG}"),
    ("R1", "a prohibition reaches past any other word", PARSER,
     'return all(_filler(w) or w in governs | PASSES_ON for w in words)', 'return True', RULES, NEG),
    ("R2", "a prohibition stops at filler", PARSER,
     'return all(_filler(w) or w in governs | PASSES_ON for w in words)',
     'return all(w in governs | PASSES_ON for w in words)', RULES, GOV),
    ("R32", "no verb hands a prohibition on", PARSER,
     'return all(_filler(w) or w in governs | PASSES_ON for w in words)',
     'return all(_filler(w) or w in governs for w in words)', RULES, GOV),
    ("P0", "punctuation does not end a prohibition", PARSER,
     '        if PUNCTUATION.search(between):\n            return False\n', '', RULES, PUNCT),
    ("P1", "a quote mark is not punctuation", PARSER,
     r'''|(?<!\w)['’]|['’](?!\w)")''', '")', RULES, PUNCT),
    ("R4", "ask verbs joined under one negator end its reach", PARSER,
     'between = JOINED_ASKS.sub(" ", before[last.end():])', 'between = before[last.end():]', RULES, GOV),
    ("R6", "a double negative negates", PARSER,
     '    if content[:1] and content[0] in DOUBLE_NEGATIVE:\n        return False\n', '', RULES, CATCHES),
    ("R7", "the verb that governs a command line ends the reach", PARSER,
     'not _negated(text, at, governs=COMMAND_VERBS)', 'not _negated(text, at)', RULES, PASSES),
    ("R34", "an adverb ends a prohibition", PARSER,
     ' or (word.endswith("ly") and len(word) > 4)', '', RULES, GOV),
    ("S15", "a plain negation crosses a comma", PARSER,
     'if "," in between or CONNECTOR.search(between):', 'if CONNECTOR.search(between):', RULES, CATCHES),
    ("R5", "a connector keeps a plain negation or a refusal", PARSER,
     'if "," in between or CONNECTOR.search(between):', 'if "," in between:', RULES, CATCHES),
    ("R29", "a plain negator reaches any later verb", PARSER,
     '    return bool(tail) and all(_filler(w) for w in tail)', '    return True', RULES, PLAIN),
    ("R30", "a plain negator reaches a verb straight after its word", PARSER,
     'return bool(tail) and all(', 'return all(', RULES, PLAIN),
    ("R31", "a plain negator before the ask alone", PARSER,
     'if last.group("refuse") or not content:', 'if last.group("refuse"):', RULES, GOV),
    # O-SECRET: assignments and reads
    ("S24", "assignment forms not read", PARSER,
     'for m in _assignment().finditer(text)]', 'for m in []]', RULES, CATCHES),
    ("S25", "a value that is a variable reads as literal", PARSER,
     r'(?P<posix>{names})=(?![\s$`<]|$)', r'(?P<posix>{names})=(?![\s<]|$)', RULES, PASSES),
    ("S26", "a placeholder reads as literal", PARSER,
     r'(?P<posix>{names})=(?![\s$`<]|$)', r'(?P<posix>{names})=(?![\s$`]|$)', RULES, PASSES),
    ("S27", "an unmasked Read-Host excused", PARSER,
     r'\s*=\s*(?!\[|\$(?!', r'\s*=\s*(?!Read-Host\b|\(|\[|\$(?!', RULES, f"{CATCHES} or {SHOWN}"),
    ("S30", "a .NET call reads as a literal", PARSER,
     r'\s*=\s*(?!\[|\$(?!', r'\s*=\s*(?!\$(?!', RULES, PASSES),
    ("S28", "a negated assignment fires", PARSER,
     'and not _negated(text, at, governs=COMMAND_VERBS):', ':', RULES, PASSES),
    ("S29", "`export X=abc` counted twice", PARSER,
     'asked = any(p.endswith(f" {name}") for p in problems)', 'asked = False', RULES,
     "test_a_verb_and_an_assignment_on_one_credential_are_one_ask"),
    ("R8", "setx not read", PARSER, r'rf"|\bsetx\s+(?:/\w+\s+)*', r'rf"|\bsetxzz\s+(?:/\w+\s+)*', RULES, SHOWN),
    ("R9", "setx's switches not skipped", PARSER, r'rf"|\bsetx\s+(?:/\w+\s+)*', r'rf"|\bsetx\s+', RULES, SHOWN),
    ("R10", "SetEnvironmentVariable not read", PARSER,
     r'''\s*,\s*[\"'][^\"']", re.IGNORECASE)''', r'''\s*,\s*[\"'][^\"']zzz", re.IGNORECASE)''', RULES, SHOWN),
    ("R11", "SetEnvironmentVariable's non-literal value read as literal", PARSER,
     r'''\s*,\s*[\"'][^\"']", re.IGNORECASE)''', r'''\s*,\s*\S", re.IGNORECASE)''', RULES, MASKED),
    ("R12", "$(Read-Host ...) excused as a variable", PARSER,
     r'(?!\[|\$(?!\(\s*Read-Host\b)|<', r'(?!\[|\$|<', RULES, SHOWN),
    ("R36", "${env:X} not read", PARSER, r'\$\{{?env:(?P<ps>', r'\$env:(?P<ps>', RULES, SHOWN),
    ("R37", "New-Item -Value not read", PARSER, r'rf"|\b(?:New|Set)-Item\b', r'rf"|\b(?:Zzz)-Item\b', RULES, SHOWN),
    ("R38", "New-Item's variable value read as literal", PARSER,
     r'''(?=[^\n;|]*-Value\s+[\"']?[^\s\"'$(<])''', r'(?=[^\n;|]*-Value\s+\S)', RULES, MASKED),
    ("R13", "a read into a variable not followed", PARSER,
     'sorted([*assigned, *_unmasked_reads(text)]', 'sorted([*assigned]', RULES, SHOWN),
    ("R14", "a bash read naming a credential not read", PARSER,
     'if words[-1:] and words[-1] in names:', 'if False:', RULES, SHOWN),
    ("R15", "a masked Read-Host into a variable fires", PARSER,
     '        if re.search(r"-(?:MaskInput|AsSecureString)\\b", read.group(2), re.IGNORECASE):\n            continue\n',
     '', RULES, MASKED),
    ("R16", "the variable's later set not found", PARSER,
     'found = set_from.search(text, read.end())', 'found = None', RULES, SHOWN),
    ("R17", "$(Read-Host -MaskInput) not the hidden form", PARSER,
     r'\s*=\s*\$?\(?\s*Read-Host\b[^;|]*-MaskInput\b', r'\s*=\s*\(?\s*Read-Host\b[^;|]*-MaskInput\b', RULES, MASKED),
    # O-SECRET: the hidden-input form
    ("R18", "the form answers any verb", PARSER,
     'if m.group(1).lower() in FORM_ANSWERS and any(', 'if any(', RULES, HANDOVER),
    ("S18", "the form on the next line not honoured", PARSER,
     'or (below and per_session_hidden(below, n))', '', RULES, f"{NEXT} or {OWN}"),
    ("S19", "any next line's form honoured for any name", PARSER,
     'or (below and per_session_hidden(below, n))',
     'or (below and any(per_session_hidden(below, v) for v in _credential_variables()))', RULES, NEXT),
    ("S20", "a code fence's line hides the form", PARSER,
     'if ln.strip() and not FENCE.match(ln)), "")', 'if ln.strip()), "")', RULES, NEXT),
    ("R19", "a hidden read earlier in the block not honoured", PARSER,
     '\n            or any(per_session_hidden("; ".join([*above[i:], line]), n) for i in range(len(above)))', '',
     RULES, TWO),
    ("R40", "only the line just above read, inside a block too", PARSER,
     'lines[fences[-1] + 1:] if len(fences) % 2 else lines[-1:]', 'lines[-1:]', RULES, TWO),
    ("R41", "the whole block above read as one, not from the read on", PARSER,
     'per_session_hidden("; ".join([*above[i:], line]), n) for i in range(len(above))',
     'per_session_hidden("; ".join([*above, line]), n) for i in range(1)', RULES, TWO),
    ("R42", "an earlier block's read honoured", PARSER,
     'lines[fences[-1] + 1:] if len(fences) % 2 else lines[-1:]',
     '[ln for ln in lines if not FENCE.match(ln)] if len(fences) % 2 else lines[-1:]', RULES, TWO),
    # O-CMD
    ("C1", "a --fields body not expanded", PARSER,
     'given = _field_options(argv, s.body)', 'given = []', RULES, FIELDS),
    ("C2", "the body's errors swallowed", PARSER,
     'except UsageError as exc:\n                return f"{\' \'.join(argv)}: {exc}"',
     'except UsageError:\n                given = []', RULES, FIELDS),
    ("C3", "a line with no body must still parse whole", PARSER,
     'complete = complete and s.body is not None', 'pass', RULES, NOBODY),
    ("C4", "a heredoc's body read as commands", PARSER,
     'held = (command, opened.group(2), [])', 'yield command, None', RULES,
     "test_a_heredocs_body_is_not_read_as_commands or " + FIELDS),
    ("C5", "an unclosed heredoc gets a body", PARSER,
     '                yield held[0], None\n                held = None\n            in_fence',
     '                yield held[0], "".join(held[2])\n                held = None\n            in_fence', RULES,
     "test_a_heredocs_body_is_not_read_as_commands"),
    ("C6", "the expansion reads stdin", PARSER,
     'read=lambda _: body)', ')', RULES, FIELDS),
    ("C7", "credentials.py's placeholder back", "src/aew/cli/credentials.py",
     'put `--print-credential` straight after `aew` to get it on standard "\n            "output")',
     'run `aew --print-credential <command>` to get it on standard "\n            "output")', RULES,
     "test_the_refusal_that_offers_print_credential_parses"),
    # the ratchet (#332's review)
    ("F1", "the base list refuses a retired rule", RATCHET,
     'allowed.parse(base_text, known_rules=False)', 'allowed.parse(base_text)', RULES,
     "test_a_rule_dropped_from_the_modes_counts_as_lowered"),
    ("F2", "an undecided run claims no stale", ALLOWED,
     '["no new, stale or added keys" if v.stale_decided else "no new or added keys"]',
     '["no new, stale or added keys"]', RULES, "test_a_run_that_decided_nothing_stale"),
    ("F3", "a stale static key told about a test", ALLOWED,
     'if key in v.stale and is_static(key):', 'if False:', RULES, "test_a_stale_static_key_names_the_scan"),
    ("F4", "no one command for many stale keys", ALLOWED,
     'if len(stale_failing) > 1:', 'if False:', RULES, "test_many_stale_keys_get_one_command"),
    ("F6", "--write keeps a residual past its key", RATCHET,
     'kept = [r for k, r in residuals.items() if k in keys]', 'kept = list(residuals.values())', RULES,
     "test_write_drops_a_residual_with_its_key"),
    ("F7a", "a base modes named and absent passes", RATCHET,
     'if on_pr and args.base_modes is not None:',
     'if on_pr and args.base_modes is not None and args.base_modes.is_file():', RULES,
     "test_a_base_modes_named_and_absent_fails"),
    ("F7b", "a base modes that exits escapes", RATCHET,
     'except (Exception, SystemExit) as exc:', 'except Exception as exc:', RULES,
     "test_a_base_modes_named_and_absent_fails"),
    ("F7c", "ci.yml skips a failed read again", ".github/workflows/ci.yml",
     '            git show "$GITHUB_SHA^1:tests/helpers/discovery/modes.py" > "$RUNNER_TEMP/modes-base.py" \\\n'
     '              || rm -f "$RUNNER_TEMP/modes-base.py"  # the ratchet fails on a base it cannot read\n'
     '            base+=(--base-modes "$RUNNER_TEMP/modes-base.py")\n',
     '            if git show "$GITHUB_SHA^1:tests/helpers/discovery/modes.py" > "$RUNNER_TEMP/modes-base.py"; then\n'
     '              base+=(--base-modes "$RUNNER_TEMP/modes-base.py")\n            fi\n', CI, GATE),
]


def generated() -> list[tuple[str, str, str, str, str, str, str]]:
    """One line per mark the punctuation check alone guards (";" and ":" end the sentence first), and one per word of
    the rule's own CONNECTOR, read from rules.py beside these tests (derived, never restated)."""
    lines = []
    punctuation = r'''PUNCTUATION = re.compile(r"[^\w\s`'’'''
    for label, mark in (("hyphen", r"\-"), ("en dash", "–"), ("em dash", "—"), ("bracket", "("),
                        ("square bracket", r"\["), ("comma", ","), ("double quote", r"\x22")):
        lines.append((f"P-{label}", f"a {label} is not punctuation", PARSER, punctuation, punctuation + mark, RULES,
                      PUNCT))
    source = (Path(__file__).resolve().parents[1] / "helpers" / "discovery" / "rules.py").read_text(encoding="utf-8")
    segment = source[source.index("CONNECTOR = re.compile("):]
    segment = re.sub(r'"\s*r"', "", segment[:segment.index("IGNORECASE")])
    words = re.search(r"\(\?:([a-z|]+)\)", segment)
    assert words, "CONNECTOR's words not found in rules.py"
    for word in words.group(1).split("|"):
        lines.append((f"K-{word}", f"'{word}' read as filler", PARSER, 'FILLER = frozenset({"ever",',
                      f'FILLER = frozenset({{"{word}", "ever",', RULES, CONNECT))
    return lines


LINES += generated()
LINES.append(("R45", "${env:X} = $v after an unmasked read not followed", PARSER,
              r'rf"\$\{{?env:{re.escape(name)}\}}?\s*=\s*\${read.group(1)}\b"',
              r'rf"\$env:{re.escape(name)}\s*=\s*\${read.group(1)}\b"', RULES, SHOWN))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clear(root: Path) -> None:
    for cache in root.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)


def run(root: Path, test: str, expr: str, timeout: int = 200) -> tuple[str, str]:
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(root / "src"), str(root / "tests" / "helpers")]),
           "PYTHONDONTWRITEBYTECODE": "1"}
    cmd = [sys.executable, "-B", "-m", "pytest", "-q", "-p", "no:xdist", "-p", "no:cacheprovider", test, "-k", expr]
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        r = subprocess.run(cmd, cwd=root, env=env, capture_output=True, text=True, timeout=timeout, creationflags=flags)
    except subprocess.TimeoutExpired:
        return "hung", f"timed out after {timeout}s"
    tail = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr.strip()[-200:]
    return ("passed" if r.returncode == 0 else "failed" if r.returncode == 1 else f"exit {r.returncode}"), tail


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    checkout, out = Path(sys.argv[1]), Path(sys.argv[2])
    wanted = set(sys.argv[3:])
    head = subprocess.run(["git", "-C", str(checkout), "rev-parse", "HEAD"], capture_output=True, text=True,
                          check=True).stdout.strip()
    results = []
    with tempfile.TemporaryDirectory(prefix="d2abl", ignore_cleanup_errors=True) as tmp:
        root = Path(tmp) / "tree"
        root.mkdir()
        archive = Path(tmp) / "head.tar"
        subprocess.run(["git", "-C", str(checkout), "-c", "core.longpaths=true", "archive", "--format=tar", "-o",
                        str(archive), "HEAD", "src", "tests", "tools", "docs", ".github", "pyproject.toml",
                        "AGENTS.md"], check=True)
        with tarfile.open(archive) as tar:
            tar.extractall(root, filter="data")
        lines = [ln for ln in LINES if not wanted or ln[0] in wanted]
        for test, expr in sorted({(ln[5], ln[6]) for ln in lines}):
            state, tail = run(root, test, expr)
            if state != "passed":
                print(f"CLEAN COPY NOT GREEN: {test} -k {expr}: {tail}")
                return 2
        for ident, what, rel, old, new, test, expr in lines:
            path = root / rel
            before, digest = path.read_bytes(), sha(path)
            text = before.decode()
            if text.count(old) != 1:
                print(f"{ident}: the text occurs {text.count(old)} times in {rel}", flush=True)
                results.append({"id": ident, "what": what, "file": rel, "test": test, "k": expr,
                                "state": "text not found", "tail": ""})
                continue
            path.write_bytes(text.replace(old, new).encode())
            clear(root)
            state, tail = run(root, test, expr)
            path.write_bytes(before)
            clear(root)
            assert sha(path) == digest
            print(f"{ident} {state:7} {what} :: {tail}", flush=True)
            results.append({"id": ident, "what": what, "file": rel, "old": old, "new": new, "test": test, "k": expr,
                            "state": state, "tail": tail})
    out.write_text(json.dumps({"head": head, "results": results}, indent=1) + "\n", encoding="utf-8")
    bad = [r["id"] for r in results if r["state"] not in ("failed", "hung")]
    print(f"{len(results) - len(bad)} of {len(results)} killed at {head[:8]}" + (f"; NOT KILLED: {bad}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
