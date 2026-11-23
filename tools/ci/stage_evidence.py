"""Stage bounded evidence, mask scanner findings, and publish only verified output."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path
from tempfile import TemporaryDirectory
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests" / "helpers"))
from bounds import EVIDENCE_BUNDLE_SCAN_S, EVIDENCE_SCAN_S  # noqa: E402
from evidence_files import (  # noqa: E402
    failure_or_death,
    failure_overflow,
    is_link,
    owner,
    publishable,
    report_json,
    state,
)

JOB_CAP = 64 * 1024 * 1024
INDEX_CAP = 64 * 1024
FINDINGS_EXIT = 23
CONFIG = Path(__file__).with_name("evidence-gitleaks.toml").resolve()
SAFE_PART = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*\Z")
WORKDIR_TEXT = {".stdout", ".stderr", ".log", ".txt", ".jsonl", ".json", ".yaml", ".yml", ".md", ".py"}


def visible(part: str) -> str:
    if SAFE_PART.fullmatch(part):
        return part
    digest = hashlib.sha256(part.encode()).hexdigest()[:12]
    return f"file-{digest}-{re.sub(r'[^A-Za-z0-9_.-]', '_', part)[-90:]}"


@dataclass(frozen=True)
class Hit:
    rule: str
    line: int
    value: bytes
    end_line: int
    decoded: bool = False


def findings(report: Path, candidate: Path, staged: set[Path]) -> dict[Path, list[Hit]]:
    """Accept only findings that can be attributed to an exact staged file."""
    hits = json.loads(report.read_text(encoding="utf-8"))
    if not isinstance(hits, list) or not hits:
        raise ValueError("missing gitleaks findings")
    withheld: dict[Path, list[Hit]] = {}
    for hit in hits:
        if not isinstance(hit, dict) or not isinstance(hit.get("File"), str):
            raise ValueError("missing gitleaks file")
        path = Path(hit["File"])
        if path.is_absolute():
            path = path.relative_to(candidate)
        elif path not in staged:
            path = (candidate.parent / path).relative_to(candidate)
        rule = hit.get("RuleID")
        if path not in staged or not isinstance(rule, str) or not SAFE_PART.fullmatch(rule):
            raise ValueError("unattributable gitleaks finding")
        line = hit.get("StartLine")
        if type(line) is not int or line < 1:
            raise ValueError("missing gitleaks line")
        value = hit.get("Secret") or hit.get("Match")
        if not isinstance(value, str) or not value:
            raise ValueError("missing gitleaks value")
        end = hit.get("EndLine", line)
        if type(end) is not int or end < line:
            raise ValueError("invalid gitleaks end line")
        withheld.setdefault(path, []).append(Hit(rule, line, value.encode(), end))
    return withheld


def scan(candidate: Path, report: Path, staged: set[Path], timeout: float = EVIDENCE_SCAN_S) -> dict[Path, list[Hit]]:
    # Match and Secret are needed for masking. This unredacted report stays
    # outside the upload directory, and the captured scanner output is never printed.
    report.unlink(missing_ok=True)
    result = subprocess.run(
        ["gitleaks", "dir", "--no-banner", "--ignore-gitleaks-allow", "--report-format", "json",
         "--config", str(CONFIG), "--exit-code", str(FINDINGS_EXIT),
         "--report-path", str(report), str(candidate)],
        cwd=report.parent, capture_output=True, timeout=timeout, check=False,
    )
    if result.returncode == 0:
        return {}
    if result.returncode != FINDINGS_EXIT:
        raise ValueError("gitleaks failed")
    return findings(report, candidate, staged)


TOKEN_TAIL = re.compile(rb"[A-Za-z0-9_./+=-]*")


def values(group: dict[Path, list[Hit]]) -> dict[bytes, str]:
    return {hit.value: hit.rule for path in sorted(group) for hit in group[path]}


def occurrences(data: bytes, secrets: dict[bytes, str]):
    for value, rule in secrets.items():
        start = data.find(value)
        while start >= 0:
            yield start, rule, value
            start = data.find(value, start + 1)


def mask_bytes(original: bytes, secrets: dict[bytes, str], *, xml: bool = False,
               whole_lines: bool = False) -> tuple[bytes, set[tuple[str, int]]]:
    spans = []
    notes = set()
    for start, rule, value in occurrences(original, secrets):
        tail = TOKEN_TAIL.match(original, start + len(value))
        assert tail is not None
        end = tail.end()
        if whole_lines:
            start = original.rfind(b"\n", 0, start) + 1
            newline = original.find(b"\n", end)
            end = len(original) if newline == -1 else newline
        spans.append((start, end, rule))
        notes.add((rule, original.count(b"\n", 0, start) + 1))
    merged: list[tuple[int, int, str]] = []
    for start, end, rule in sorted(spans):
        if merged and start < merged[-1][1]:
            left, right, first_rule = merged.pop()
            merged.append((left, max(right, end), first_rule))
        else:
            merged.append((start, end, rule))
    if merged:
        chunks = []
        cursor = 0
        for start, end, rule in merged:
            marker = f"<redacted:{rule}>"
            if xml:
                marker = marker.replace("<", "&lt;").replace(">", "&gt;")
            chunks.extend((original[cursor:start], marker.encode(),
                           b"\n" * original.count(b"\n", start, end)))
            cursor = end
        return b"".join([*chunks, original[cursor:]]), notes
    return original, notes


def map_strings(value, transform):
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            masked = transform(key)
            if masked in result:
                masked += "-" + hashlib.sha256(key.encode()).hexdigest()[:12]
            result[masked] = map_strings(item, transform)
        return result
    if isinstance(value, list):
        return [map_strings(item, transform) for item in value]
    return transform(value) if isinstance(value, str) else value


def map_xml(data: bytes | str, transform) -> str:
    class PlainXML(ElementTree.TreeBuilder):
        def doctype(self, *args):
            raise ValueError("document types are outside the JUnit format")

    parser = ElementTree.XMLParser(target=PlainXML())  # noqa: S314 -- reject DTDs before entity expansion
    parser.feed(data)
    root = parser.close()
    for element in root.iter():
        element.attrib.update((key, transform(value)) for key, value in element.attrib.items())
        if element.text:
            element.text = transform(element.text)
        if element.tail:
            element.tail = transform(element.tail)
    return ElementTree.tostring(root, encoding="unicode")


def mask(file: Path, secrets: dict[bytes, str], *, whole_lines: bool = False) -> set[tuple[str, int]]:
    data = file.read_bytes()
    if file.suffix == ".json" or (whole_lines and file.suffix == ".xml"):
        notes = set()

        def transform(value: str) -> str:
            masked, lines = mask_bytes(value.encode("utf-8"), secrets, whole_lines=whole_lines)
            notes.update(lines)
            return masked.decode("utf-8")

        if file.suffix == ".json":
            masked = json.dumps(map_strings(json.loads(data), transform), indent=1) + "\n"
        else:
            masked = map_xml(data, transform)
        if notes:
            file.write_text(masked, encoding="utf-8")
    else:
        masked_data, notes = mask_bytes(data, secrets, xml=file.suffix == ".xml", whole_lines=whole_lines)
        if notes:
            file.write_bytes(masked_data)
    return notes


def mask_reported_lines(file: Path, group: list[Hit]) -> None:
    """Retain surrounding context even when a decoder's finding has no literal match in the output."""
    by_line = {}
    for hit in group:
        if file.suffix in {".json", ".xml"} and not hit.decoded:
            continue  # JSON's decoded view supplies lines inside individual keys and values.
        for number in range(hit.line, hit.end_line + 1):
            by_line[number] = f"<redacted:{hit.rule}>"
    if not by_line:
        return
    next_line = 1

    def marked(value: str) -> str:
        nonlocal next_line
        lines = value.split("\n")
        for i in range(len(lines)):
            if next_line in by_line:
                lines[i] = by_line[next_line]
            next_line += 1
        return "\n".join(lines)

    data = file.read_text(encoding="utf-8")
    if file.suffix == ".json":
        data = json.dumps(map_strings(json.loads(data), marked), indent=1) + "\n"
    elif file.suffix == ".xml":
        data = map_xml(data, marked)
    else:
        data = marked(data)
    file.write_text(data, encoding="utf-8")


def scan_material(candidate: Path, report: Path, staged: set[Path], paths: list[str], deadline: float):
    # A multiline PEM in JSON has escaped newlines on disk. Scan decoded values and paths as private input too.
    # The input directory is removed before the upload directory can be moved into place.
    with TemporaryDirectory(prefix="scan-input-", dir=candidate) as tmp:
        root = Path(tmp)
        paths_file = root / "paths.txt"
        paths_file.write_text("\n".join(paths), encoding="utf-8")
        aliases = {paths_file.relative_to(candidate): Path("inventory.txt")}
        for path in sorted(staged):
            if path.suffix not in {".json", ".xml"}:
                continue
            expanded = root / (hashlib.sha256(path.as_posix().encode()).hexdigest() + ".txt")
            strings = []

            def observe(value, strings=strings):
                strings.append(value)
                return value

            data = (candidate / path).read_bytes()
            if path.suffix == ".json":
                map_strings(json.loads(data), observe)
            else:
                try:
                    map_xml(data, observe)
                except (ValueError, ElementTree.ParseError):
                    continue  # malformed XML still receives the ordinary raw-text scan
            expanded.write_text("\n".join(strings), encoding="utf-8")
            aliases[expanded.relative_to(candidate)] = path
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError("scanner time budget expired")
        hits = scan(candidate, report, staged | aliases.keys(), min(EVIDENCE_SCAN_S, remaining))
        attributed = {}
        for path, group in hits.items():
            decoded = path in aliases and path != paths_file.relative_to(candidate)
            attributed.setdefault(aliases.get(path, path), []).extend(replace(hit, decoded=decoded) for hit in group)
        return attributed


def write_inventory(directory: Path, rows: list[str]) -> None:
    # Keep every omission and index row while bounding each metadata file. The primary inventory declares all parts.
    chunks = [bytearray()]
    reserve = len("inventory parts: 999999999\n")
    for row in rows:
        data = row.encode("utf-8")
        if len(chunks[-1]) + len(data) > INDEX_CAP - reserve and chunks[-1]:
            chunks.append(bytearray())
        chunks[-1].extend(data)
    for i, chunk in enumerate(chunks):
        if i == 0:
            if len(chunks) > 1:
                chunk.extend(f"inventory parts: {len(chunks) - 1}\n".encode())
            (directory / "inventory.txt").write_bytes(chunk)
        else:
            (directory / f"inventory-part-{i}.txt").write_bytes(chunk)


def stage(source: Path, destination: Path, *, reports_only: bool = False) -> str:
    source, destination = source.absolute(), destination.absolute()
    if destination.exists():
        raise FileExistsError(destination)
    with TemporaryDirectory(dir=destination.parent) as temporary:
        candidate = Path(temporary) / "contents"
        candidate.mkdir()
        left = JOB_CAP - INDEX_CAP
        omissions: list[tuple[Path, str]] = []
        staged: set[Path] = set()
        ablation = os.environ.get("AEW_EVIDENCE_ABLATE") if os.environ.get("AEW_EVIDENCE_PLANT") == "failure" else None

        def files():
            if not source.is_dir() or is_link(source):
                return
            for directory, subdirs, names in os.walk(source):
                root = Path(directory)
                for name in sorted(subdirs.copy()):
                    if is_link(root / name):
                        subdirs.remove(name)
                        omissions.append(((root / name).relative_to(source), "linked directory"))
                yield from (root / name for name in names)

        for file in sorted(files(), key=lambda p: (not failure_or_death(p.relative_to(source)), p)):
            relative = file.relative_to(source)
            if reports_only and not (report_json(relative) or failure_overflow(relative)):
                continue
            if relative.parent == Path(".") and relative.match("inventory-part-*.txt"):
                omissions.append((relative, "reserved publication index name"))
                continue
            if owner(relative) is None:
                anonymous = Path("file-" + hashlib.sha256(relative.as_posix().encode()).hexdigest()[:12])
                omissions.append((anonymous, "unlisted writer"))
                continue
            if not publishable(relative):
                omissions.append((relative, "filtered file class"))
                continue
            try:
                if any(is_link(p) for p in (file, *file.parents) if p.is_relative_to(source)) or not file.is_file():
                    omissions.append((relative, "link, non-file, or excluded private workdir file"))
                    continue
                if "workdir" in relative.parts:
                    original = Path(file.name.removesuffix(".txt"))
                    forbidden = any(word in part.lower() for part in relative.parts
                                    for word in ("credential", "secret", "auth.json", ".env", ".git"))
                    if forbidden or (original.suffix.lower() not in WORKDIR_TEXT
                                     and original.name != "heartbeat"):
                        omissions.append((relative, "excluded private workdir file"))
                        continue
                with file.open("rb") as stream:
                    limit = None if failure_overflow(relative) else min(left, JOB_CAP if report_json(relative)
                                                                         else 4 * 1024 * 1024)
                    data = stream.read() if limit is None else stream.read(limit + 1)
                if limit is not None and len(data) > limit:
                    omissions.append((relative, "job cap" if limit == left else "per-file size limit"))
                    continue
                if b"\x00" in data:
                    omissions.append((relative, "contains NUL"))
                    continue
                content = data.decode("utf-8")
                if report_json(relative):
                    try:
                        json.loads(content)
                    except ValueError:
                        omissions.append((relative, "invalid JSON"))
                        continue
                if file.name in {"junit.xml", "vertical-summary.txt"}:
                    from aew.harness.defects import redact_text

                    content = redact_text(content)
                    if file.suffix == ".xml":
                        content = content.replace("<redacted>", "&lt;redacted&gt;")
                    data = content.encode("utf-8")
            except (OSError, UnicodeError) as exc:
                omissions.append((relative, "not UTF-8" if isinstance(exc, UnicodeError) else "unreadable"))
                continue
            parts = tuple(visible(part) for part in relative.parts)
            if "workdir" in relative.parts and ".aew" in relative.parts:
                index = relative.parts.index("workdir")
                parts = (*parts[:index], "harness", *parts[index + 1:])
            out = candidate.joinpath(*parts)
            if out.exists():
                omissions.append((relative, "duplicate staged name"))
                continue
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(data)
            staged.add(out.relative_to(candidate))
            if not failure_overflow(relative):
                left = max(0, left - len(data))

        report = Path(temporary) / "scan.json"

        def shown(path: Path) -> str:
            name = "/".join(visible(part) for part in path.parts)
            if any(occurrences(name.encode(), secrets)):
                return "file-" + hashlib.sha256(name.encode()).hexdigest()[:12]
            return name

        deadline = time.monotonic() + EVIDENCE_BUNDLE_SCAN_S

        def scan_current():
            paths = [shown(path) for path in staged] + [shown(path) for path, _ in omissions]
            return scan_material(candidate, report, staged, paths, deadline)

        secrets = {}
        masked: dict[Path, set[tuple[str, int]]] = {}
        try:
            initial = scan_current()
            hits = initial
            for whole_lines in (False, True):
                if not hits:
                    break
                secrets.update(values(hits))
                for path in sorted(staged):
                    notes = mask(candidate / path, secrets, whole_lines=whole_lines)
                    if notes:
                        masked.setdefault(path, set()).update(notes)
                    if any(occurrences(path.as_posix().encode(), secrets)):
                        digest = hashlib.sha256(path.as_posix().encode()).hexdigest()
                        target = (Path("masked-" + digest + ".json") if report_json(path)
                                  else Path("autopsy", "masked-" + digest + ".txt"))
                        (candidate / target).parent.mkdir(parents=True, exist_ok=True)
                        (candidate / path).rename(candidate / target)
                        staged.remove(path)
                        staged.add(target)
                        masked[target] = masked.pop(path, set()) | {("path", 0)}
                hits = scan_current()
            if hits:
                # A logical match can survive span replacement. Use the scanner's reported line range.
                for path, group in hits.items():
                    if path not in staged:
                        raise ValueError("unverifiable inventory")
                    mask_reported_lines(candidate / path, group)
                    masked.setdefault(path, set()).update((hit.rule, hit.line) for hit in group)
                if scan_current():
                    raise ValueError("scanner could not verify masked output")

            if ablation == "overflow":
                for path in sorted(staged):
                    if failure_overflow(path):
                        (candidate / path).unlink()
                        staged.remove(path)
                        omissions.append((path, "overflow publication ablated"))
            if ablation == "mask":
                # The control models a withhold-only publisher without ever uploading an unscanned payload.
                for path in sorted(masked):
                    (candidate / path).unlink()
                    staged.remove(path)
                    omissions.append((path, "masking ablated; withheld"))
            left = JOB_CAP - INDEX_CAP
            for path in sorted(staged, key=lambda p: (not failure_or_death(p), p)):
                if failure_overflow(path):
                    continue
                size = (candidate / path).stat().st_size
                if size > left:
                    (candidate / path).unlink()
                    staged.remove(path)
                    omissions.append((path, "job cap after masking"))
                else:
                    left -= size
            status = f"gitleaks masked {len(masked)} files" if initial else "gitleaks clean"

            def inventory_rows():
                rows = [f"{status}\n", f"{len(staged)} candidate files, {len(omissions)} omitted\n",
                        "finding inventory.txt (publisher)\n"]
                for path in sorted(masked):
                    for rule, line in sorted(masked[path]):
                        rows.append(f"masked {shown(path)}:{line} ({rule})\n")
                for path in sorted(staged):
                    classification = state(path, (candidate / path).read_bytes())
                    rows.append(f"{classification} {shown(path)} ({owner(path)})\n")
                for path, reason in omissions:
                    rows.append(f"omitted {shown(path)} ({reason})\n")
                    if failure_or_death(path):
                        rows.append(f"evidence defect: {shown(path)}: withheld/omitted ({reason})\n")
                return rows

            # A long omission inventory can outgrow its initial reservation. Evict the lowest priority payloads
            # first, while always retaining the full failure overflow and a record for every omitted file.
            eligible = sorted((path for path in staged if not failure_overflow(path)),
                              key=lambda p: (not failure_or_death(p), p))
            while True:
                for index in candidate.glob("inventory*.txt"):
                    index.unlink()
                write_inventory(candidate, inventory_rows())
                indexes_size = sum(index.stat().st_size for index in candidate.glob("inventory*.txt"))
                excess = indexes_size - INDEX_CAP - left
                if excess <= 0 or not eligible:
                    break
                while excess > 0 and eligible:
                    path = eligible.pop()
                    size = (candidate / path).stat().st_size
                    (candidate / path).unlink()
                    staged.remove(path)
                    omissions.append((path, "job cap including inventory"))
                    left += size
                    excess -= size
            candidate.rename(destination)
        except (OSError, ValueError, ElementTree.ParseError, subprocess.TimeoutExpired):
            status = "gitleaks scan unavailable; evidence defect: scan unavailable"
            destination.mkdir()
            (destination / "inventory.txt").write_text(
                status + "\nfinding inventory.txt (publisher)\n", encoding="utf-8")
        return status


def main(argv: list[str]) -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--reports-only", action="store_true")
    args = parser.parse_args(argv)
    source, destination = args.source, args.destination
    started = time.monotonic()
    print(stage(source, destination, reports_only=args.reports_only))
    print(f"evidence timing stage {time.monotonic() - started:.3f}s", file=sys.stderr)
    for line in (destination / "inventory.txt").read_text(encoding="utf-8").splitlines():
        if line.startswith(("masked ", "withheld ")):
            print(line, file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1:])
