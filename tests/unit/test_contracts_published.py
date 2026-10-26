"""docs/contracts/ is the adopted design text, published sanitised (D-A, the operator's decision of 2026-10-25).

It is the design workspace's generator output, byte for byte, and nobody edits it by hand. The generator and its own
check stay in the private workspace, which runs them against main. This test holds what the repository alone can hold:
every copy is in MANIFEST.json and every entry is on disk, each copy's bytes match its sha256, and each header agrees
with its entry. It reads only docs/contracts/.
"""
import hashlib
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "docs" / "contracts"
OWN = ("README.md", "MANIFEST.json")  # the tree's own files, not copies
FIELDS = ("generated", "position", "source", "source-sha256", "edits-sha256")
# The header patterns, verbatim from the generator, matched at byte 0.
MD_HEAD = re.compile(rb'<!--\n((?:[a-z0-9-]+: [^\n]*\n)+)-->\n\n')
YAML_HEAD = re.compile(rb'((?:# [a-z0-9-]+: [^\n]*\n)+)\n')


def header(name: str, data: bytes) -> dict[str, str] | None:
    """A markdown or YAML copy's header fields, or None when it does not parse."""
    if name.endswith(".md"):
        m = MD_HEAD.match(data)
        lines = m.group(1).decode("utf-8").splitlines() if m else None
    else:
        m = YAML_HEAD.match(data)
        lines = [line[2:] for line in m.group(1).decode("utf-8").splitlines()] if m else None
    return None if lines is None else dict(line.split(": ", 1) for line in lines)


def problems(root: Path) -> list[str]:
    """Everything wrong with a published tree, one line per problem, naming the file."""
    entries = {e["path"]: e for e in json.loads((root / "MANIFEST.json").read_text(encoding="utf-8"))["files"]}
    on_disk = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()} - set(OWN)
    found = [f"{p}: not in MANIFEST.json" for p in sorted(on_disk - entries.keys())]
    found += [f"{p}: in MANIFEST.json but missing" for p in sorted(entries.keys() - on_disk)]
    for p in sorted(on_disk & entries.keys()):
        entry, data = entries[p], (root / p).read_bytes()
        if hashlib.sha256(data).hexdigest() != entry["sha256"]:
            found.append(f"{p}: its bytes do not match its sha256")
        if p.endswith(".json"):
            if entry["header"] is not False:
                found.append(f"{p}: a JSON copy must be listed with header: false")
            continue
        fields = header(p, data)
        if fields is None:
            found.append(f"{p}: its header does not parse")
        elif fields != {f: entry[f] for f in FIELDS}:
            found.append(f"{p}: its header does not match its MANIFEST.json entry")
    return found


def test_every_published_copy_matches_its_manifest_entry():
    assert (CONTRACTS / "MANIFEST.json").is_file() and (CONTRACTS / "README.md").is_file()
    assert problems(CONTRACTS) == []


def test_the_manifest_lists_each_kind_of_copy():
    """The check above is not vacuous: the set holds markdown, YAML and JSON copies."""
    paths = [e["path"] for e in json.loads((CONTRACTS / "MANIFEST.json").read_text(encoding="utf-8"))["files"]]
    assert {Path(p).suffix for p in paths} >= {".md", ".yaml", ".json"}


# The planted control: a copy of the published tree, with one fault planted per case.

def planted(tmp_path: Path) -> Path:
    root = tmp_path / "contracts"
    shutil.copytree(CONTRACTS, root)
    return root


def first(root: Path, suffix: str) -> Path:
    return next(root / e["path"] for e in json.loads((root / "MANIFEST.json").read_text(encoding="utf-8"))["files"]
                if e["path"].endswith(suffix))


def rewrite_entry(root: Path, path: Path, **fields: object) -> None:
    manifest = json.loads((root / "MANIFEST.json").read_text(encoding="utf-8"))
    for e in manifest["files"]:
        if e["path"] == path.relative_to(root).as_posix():
            e.update(fields)
    (root / "MANIFEST.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8", newline="\n")


def test_planted_right_case_passes(tmp_path):
    assert problems(planted(tmp_path)) == []


def test_planted_changed_byte_is_found(tmp_path):
    root = planted(tmp_path)
    copy = first(root, ".md")
    data = bytearray(copy.read_bytes())
    data[-2] ^= 1
    copy.write_bytes(bytes(data))
    assert problems(root) == [f"{copy.relative_to(root).as_posix()}: its bytes do not match its sha256"]


def test_planted_unlisted_file_is_found(tmp_path):
    root = planted(tmp_path)
    (root / "A-01" / "extra.md").write_bytes(b"# not published\n")
    assert problems(root) == ["A-01/extra.md: not in MANIFEST.json"]


def test_planted_missing_copy_is_found(tmp_path):
    root = planted(tmp_path)
    copy = first(root, ".yaml")
    copy.unlink()
    assert problems(root) == [f"{copy.relative_to(root).as_posix()}: in MANIFEST.json but missing"]


def test_planted_header_that_disagrees_with_its_entry_is_found(tmp_path):
    """A header field changed with the entry's sha256 made to match, so that only the header check sees it."""
    root = planted(tmp_path)
    for suffix in (".md", ".yaml"):
        copy = first(root, suffix)
        data = copy.read_bytes().replace(b"position: A-", b"position: B-", 1)
        copy.write_bytes(data)
        rewrite_entry(root, copy, sha256=hashlib.sha256(data).hexdigest())
    assert sorted(problems(root)) == sorted(f"{first(root, s).relative_to(root).as_posix()}: its header does not match "
                                            "its MANIFEST.json entry" for s in (".md", ".yaml"))


def test_planted_unparsable_header_is_found(tmp_path):
    root = planted(tmp_path)
    copy = first(root, ".md")
    data = copy.read_bytes().replace(b"-->\n\n", b"-->\n", 1)
    copy.write_bytes(data)
    rewrite_entry(root, copy, sha256=hashlib.sha256(data).hexdigest())
    assert problems(root) == [f"{copy.relative_to(root).as_posix()}: its header does not parse"]


def test_planted_json_copy_listed_with_a_header_is_found(tmp_path):
    root = planted(tmp_path)
    copy = first(root, ".json")
    rewrite_entry(root, copy, header=True)
    assert problems(root) == [f"{copy.relative_to(root).as_posix()}: a JSON copy must be listed with header: false"]
