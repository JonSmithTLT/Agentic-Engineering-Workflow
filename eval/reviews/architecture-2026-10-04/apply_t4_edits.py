"""Edits to existing files for the ADR-0013 prototype branch (review/t4-knowledge-manifest). Run from tree/."""
from __future__ import annotations

import json
from pathlib import Path


def rw(p: str, f) -> None:
    s = Path(p).read_text(encoding="utf-8")
    s2 = f(s)
    assert s2 != s, p
    Path(p).write_text(s2, encoding="utf-8", newline="\n")
    print("edited", p)


KNOWLEDGE_BLOCK = '''    "knowledge": {
      "description": "ADR-0013 (draft): the constant-size hot side of the knowledge records in the history. capture: the last receipt and the outbox revision it covers (so status never reads the history); pending: held candidates awaiting judgment (bounded; the action projection reads it).",
      "type": "object",
      "required": ["capture", "pending"],
      "additionalProperties": false,
      "properties": {
        "capture": {
          "oneOf": [
            {"type": "null"},
            {
              "type": "object",
              "required": ["last_receipt", "through_revision"],
              "additionalProperties": false,
              "properties": {"last_receipt": {"type": "string"}, "through_revision": {"type": "integer", "minimum": 0}}
            }
          ]
        },
        "pending": {
          "type": "array",
          "maxItems": 20,
          "items": {
            "type": "object",
            "required": ["id", "version", "kind", "since"],
            "additionalProperties": false,
            "properties": {
              "id": {"type": "string"},
              "version": {"type": "integer", "minimum": 1},
              "kind": {"enum": ["reference", "case", "lesson"]},
              "class": {"type": ["string", "null"]},
              "since": {"type": "string"}
            }
          }
        },
        "pending_overflow": {"type": "integer", "minimum": 0}
      }
    },
'''

RETIRED = '''    "retired_observations": {
      "description": "Observation worktrees of archived invocations still on disk: listed until each is removed, and retried at every Lead commit (plan R7).",'''


def history_schema(s: str) -> str:
    return s.replace(
        '"kind": {"enum": ["unit", "annotation", "audit", "lead"]},',
        '"kind": {"enum": ["unit", "annotation", "audit", "lead", "reference", "case", "lesson", "disposition", "receipt"]},\n'
        '        "version": {"description": "A knowledge content version (case, lesson): a changed claim is a new record and a new entry, never a rewrite (ADR-0013 draft D3).", "type": "integer", "minimum": 1},')


def control_schema(s: str) -> str:
    s = s.replace(RETIRED, KNOWLEDGE_BLOCK + RETIRED)
    return s.replace('''            {"required": ["retained_workspaces"]},
            {"required": ["retired_observations"]}
          ]''', '''            {"required": ["retained_workspaces"]},
            {"required": ["retired_observations"]},
            {"required": ["knowledge"]}
          ]''')


def schemas_init(s: str) -> str:
    return s.replace('    "history": "history.schema.json",\n}',
                     '    "history": "history.schema.json",\n    "knowledge-case": "knowledge-case.schema.json",\n'
                     '    "knowledge-disposition": "knowledge-disposition.schema.json",\n'
                     '    "knowledge-receipt": "knowledge-receipt.schema.json",\n}')


def manifest(s: str) -> str:
    return s.replace(
        'ENTRY_KINDS = ("unit", "annotation", "audit", "lead")',
        '# Knowledge records join the manifest as entry kinds (ADR-0013 draft D1): content versions, the append-only\n'
        '# dispositions about them, and capture receipts. The manifest sequence number is the global knowledge_event_seq.\n'
        'CONTENT_KINDS = ("reference", "case", "lesson")\n'
        'KNOWLEDGE_KINDS = (*CONTENT_KINDS, "disposition", "receipt")\n'
        'ENTRY_KINDS = ("unit", "annotation", "audit", "lead", *KNOWLEDGE_KINDS)')


def store(s: str) -> str:
    s = s.replace('''RECORD_GLOBS = ("work/*/archive.yaml", "work/*/annotations/*.yaml", "history/lead/*.yaml",
                "history/lead/annotations/*.yaml", "history/audits/*.yaml")''',
                  '''RECORD_GLOBS = ("work/*/archive.yaml", "work/*/annotations/*.yaml", "history/lead/*.yaml",
                "history/lead/annotations/*.yaml", "history/audits/*.yaml",
                "knowledge/cases/*/*.yaml", "knowledge/cases/*/dispositions/*.yaml", "knowledge/lessons/*/*.yaml",
                "knowledge/lessons/*/dispositions/*.yaml", "knowledge/references/*.yaml",
                "knowledge/references/*/dispositions/*.yaml", "knowledge/receipts/*.yaml")
KNOWLEDGE_DIRS = {"case": "cases", "lesson": "lessons", "reference": "references"}''')
    return s.replace('''def annotation_rel(subject: str, seq: int) -> str:
    return f"work/{subject}/annotations/{seq:04d}.yaml"''', '''def annotation_rel(subject: str, seq: int) -> str:
    return f"work/{subject}/annotations/{seq:04d}.yaml"


def knowledge_rel(kind: str, knowledge_id: str, version: int) -> str:
    """A knowledge content version's record (ADR-0013 draft D2): immutable per version."""
    if kind == "reference":
        return f"knowledge/references/{knowledge_id}.yaml"
    return f"knowledge/{KNOWLEDGE_DIRS[kind]}/{knowledge_id}/v{version}.yaml"


def disposition_rel(subject: str, seq: int, kind: str = "case") -> str:
    """The ``seq``-th disposition about a knowledge record, beside its versions."""
    return f"knowledge/{KNOWLEDGE_DIRS.get(kind, 'cases')}/{subject}/dispositions/{seq:04d}.yaml"


def receipt_rel(receipt_id: str) -> str:
    return f"knowledge/receipts/{receipt_id}.yaml"''')


def api(s: str) -> str:
    s = s.replace('from aew.engine.integration_ops import Integration\n',
                  'from aew.engine.integration_ops import Integration\nfrom aew.engine.knowledge_ops import Knowledge\n')
    s = s.replace('        self._history = history = HistoryCommands(k, units=units, archive=archive)\n',
                  '        self._history = history = HistoryCommands(k, units=units, archive=archive)\n'
                  '        self._knowledge = Knowledge(k, archive=archive)\n')
    s = s.replace('''            "counters": {"ticket": 0, "story": 0, "epic": 0, "invocation": 0, "decision": 0, "handoff": 0},''',
                  '''            "counters": {"ticket": 0, "story": 0, "epic": 0, "invocation": 0, "decision": 0, "handoff": 0,
                         "knowledge": 0, "disposition": 0, "receipt": 0},''')
    s = s.replace('''            "cold": {"root": history_manifest.empty_root()},  # ADR-0011: finished work is archived here''',
                  '''            "cold": {"root": history_manifest.empty_root()},  # ADR-0011: finished work is archived here
            "knowledge": {"capture": None, "pending": [], "pending_overflow": 0},  # ADR-0013 (draft): the hot side''')
    return s.replace('''    def history_reindex(self) -> dict[str, Any]:
        return self._history.history_reindex()''', '''    def history_reindex(self) -> dict[str, Any]:
        return self._history.history_reindex()

    def knowledge_case(self, **kw: Any) -> dict[str, Any]:
        return self._knowledge.knowledge_case(**kw)

    def knowledge_dispose(self, **kw: Any) -> dict[str, Any]:
        return self._knowledge.knowledge_dispose(**kw)

    def knowledge_show(self, knowledge_id: str) -> dict[str, Any]:
        return self._knowledge.knowledge_show(knowledge_id)

    def knowledge_list(self, *, kind: str | None = None, limit: int = 50) -> dict[str, Any]:
        return self._knowledge.knowledge_list(kind=kind, limit=limit)

    def knowledge_search(self, query: str, *, kinds: tuple[str, ...] | None = None,
                         limit: int = 20) -> dict[str, Any]:
        return self._knowledge.knowledge_search(query, kinds=kinds, limit=limit)''')


def cli(s: str) -> str:
    s = s.replace('    from aew.cli import history_commands, work_commands\n',
                  '    from aew.cli import history_commands, knowledge_commands, work_commands\n')
    return s.replace('    history_commands.register(sub)\n',
                     '    history_commands.register(sub)\n    knowledge_commands.register(sub)\n')


def history_ops(s: str) -> str:
    return s.replace('''        checked = {"entries": report.entries, "records": report.records}
        problems, damaged = list(report.problems) + self._unclosed(closure), list(report.damaged)''',
                     '''        checked = {"entries": report.entries, "records": report.records}
        problems, damaged = list(report.problems) + self._unclosed(closure), list(report.damaged)
        if full:  # ADR-0013 (draft) D12: the knowledge entries' link checks, from the derived index, never on a commit
            from aew.engine.knowledge_ops import knowledge_problems

            try:
                problems += knowledge_problems(self.archive.index(state))
            except (IntegrityError, LockTimeout) as exc:
                problems.append(f"knowledge checks not run: {exc}")''')


def invariants(s: str) -> str:
    return s.replace('''    work, invocations, tokens = {}, {}, {}
    moves: dict[str, str | None] = {}
    for entry in history.walk(root_):
        if entry["kind"] == "unit":''', '''    work, invocations, tokens = {}, {}, {}
    moves: dict[str, str | None] = {}
    knowledge_seen: set[str] = set()  # 29. a disposition's subject is a knowledge record at a lower position
    for entry in history.walk(root_):
        if entry["kind"] in ("reference", "case", "lesson"):
            knowledge_seen.add(entry["id"])
        elif entry["kind"] == "disposition" and entry.get("subject") not in knowledge_seen:
            problems.append(f"disposition {entry['id']} precedes or lacks its subject {entry.get('subject')}")
        if entry["kind"] == "unit":''')


def knowledge_ops(s: str) -> str:
    return s.replace('sha = History.write_record(ctx.session, dump_yaml(disposition) and rel_path, dump_yaml(disposition))',
                     'sha = History.write_record(ctx.session, rel_path, dump_yaml(disposition))')


if __name__ == "__main__":
    rw("src/aew/schemas/history.schema.json", history_schema)
    rw("src/aew/schemas/control.schema.json", control_schema)
    json.loads(Path("src/aew/schemas/control.schema.json").read_text(encoding="utf-8"))
    json.loads(Path("src/aew/schemas/history.schema.json").read_text(encoding="utf-8"))
    rw("src/aew/schemas/__init__.py", schemas_init)
    rw("src/aew/history/manifest.py", manifest)
    rw("src/aew/history/store.py", store)
    rw("src/aew/engine/api.py", api)
    rw("src/aew/cli/commands.py", cli)
    rw("src/aew/engine/history_ops.py", history_ops)
    rw("tests/helpers/invariants.py", invariants)
    rw("src/aew/engine/knowledge_ops.py", knowledge_ops)
    print("all edits applied")
