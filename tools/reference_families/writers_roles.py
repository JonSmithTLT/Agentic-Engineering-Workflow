"""The CLI cut per role: which command each handler serves, and so which role runs it (STG-12 S12-2, DOC-01).

One declaring function, ``aew.cli.main:_main``, declares the CLI's roles, but a process runs one command, and the
command decides the role (``process_kind.cli_entry_point``, the owner: ``lead mcp`` and ``dashboard serve`` are the
non-writer roles, every other command is the store writer ``aew``). The CLI hands a command to its handler through
``args.handler``, which no call names, so the roles are cut by the parser instead: each
``parser.set_defaults(handler=...)`` registers the handler of the command path its parser expression spells. This module
reads those expressions (``argparse.ArgumentParser(...)`` is the empty path, ``p.add_subparsers(...)`` is the path of
``p``, ``p.add_parser("w")`` is that path and ``w``, a parameter is the argument of every static call of its function,
a name is the assignment the use reads) and gives, per role, the handlers of its commands.

A handler that cannot be placed under a command (a path spelled by something this reading does not follow) is not
guessed: it is the registering function's, and the reach treats it as run by every role.

A name is read as the assignment that dominates the use: the nearest earlier one that is not inside a branch or loop
the use is outside of, together with the later ones inside such branches (the register functions assign ``p`` and ``q``
again and again, in straight-line code, so the union of all of a name's assignments would blur every command into every
other).
"""

from __future__ import annotations

import ast
from collections import defaultdict
from collections.abc import Callable
from typing import NamedTuple

from reference_families import writers_flow as F

Key = tuple[str, str]
Path = tuple[str, ...]  # the words of a command: ("lead", "mcp")
DEPTH = 40  # names and parameters followed: a parser passes about eight steps from `build_parser` to a command
CONDITIONAL = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.Match)
BRANCHING = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)


class Roles(NamedTuple):
    """The CLI's roles, from the owner: the one a command selects by default, the ones named commands select, and
    the one the environment selects (so no command does)."""

    general: str
    named: frozenset[str]
    worker: str

    @property
    def all(self) -> frozenset[str]:
        return self.named | {self.general, self.worker}


class Registration(NamedTuple):
    """One ``set_defaults(handler=...)``: where, the command paths its parser may spell, whether it may spell one this
    reading cannot read, and the functions it names."""

    registrar: Key  # (module, function); the function is "" outside any function
    line: int
    paths: tuple[Path, ...]
    unread: bool
    handlers: tuple[Key, ...]


class Cut(NamedTuple):
    registrations: list[Registration]
    handlers: dict[str, set[Key]]  # role -> the handler functions of the commands it runs
    undecided: dict[Key, set[Key]]  # registering function -> its handlers whose command could not be read


def roles_of(cli_keys: set[str], cli_entry_point: Callable[[list[str], dict[str, str]], str], environment: str
             ) -> Roles:
    """The CLI's roles: ``cli_keys`` are the rows ``cli_entry_point`` can give. The default is the role of no words, the
    worker role is the role of no words under ``environment`` (the variable it is chosen by), and the rest are named
    by their command words."""
    general = cli_entry_point([], {})
    worker = cli_entry_point([], {environment: "1"})
    return Roles(general, frozenset(cli_keys - {general, worker}), worker)


# ------------------------------------------------------------------------------------------------------ the parsers

class _Reader:
    def __init__(self, program: F.Program) -> None:
        self.program = program
        self._blocks: dict[Key, dict[int, tuple[int, ...]]] = {}

    # -- which assignment a use reads
    def blocks(self, func: F.Func) -> dict[int, tuple[int, ...]]:
        """Node id -> the ids of the branches and loops it is inside, outermost first, in the function's own body."""
        found = self._blocks.get(func.key)
        if found is not None:
            return found
        out: dict[int, tuple[int, ...]] = {}

        def walk(node: ast.AST, chain: tuple[int, ...]) -> None:
            for child in ast.iter_child_nodes(node):
                if isinstance(child, BRANCHING):
                    continue
                out[id(child)] = chain
                walk(child, (*chain, id(child)) if isinstance(child, CONDITIONAL) else chain)

        walk(func.node, ())
        self._blocks[func.key] = out
        return out

    def reads(self, scope: F.Func, name: ast.Name, own: bool) -> tuple[list[ast.expr], bool]:
        """The assignments of ``name.id`` in ``scope`` that the use ``name`` may read, and whether an assignment the
        use does not overwrite is a parameter's (the arguments). A function enclosing the use is read as the union of
        all its assignments: it runs when the closure is called, not where it is defined."""
        assigns = scope.assigns.get(name.id, [])
        if not own:
            return list(assigns), name.id in scope.params
        before = sorted((r for r in assigns if r.lineno < name.lineno), key=lambda r: r.lineno)
        blocks = self.blocks(scope)
        use = blocks.get(id(name))
        if use is None:
            return before, name.id in scope.params
        dominating = [r for r in before if id(r) in blocks and use[: len(blocks[id(r)])] == blocks[id(r)]]
        if not dominating:
            return before, name.id in scope.params
        last = dominating[-1]
        return [last, *[r for r in before if r.lineno > last.lineno]], False

    # -- values
    def strings(self, mod: F.Module, func: F.Func | None, expr: ast.expr, depth: int, seen: frozenset[tuple[Key, str]]
                ) -> set[str | None]:
        if depth <= 0:
            return {None}
        if isinstance(expr, ast.Constant):
            return {expr.value} if isinstance(expr.value, str) else {None}
        if isinstance(expr, ast.IfExp):
            return (self.strings(mod, func, expr.body, depth - 1, seen)
                    | self.strings(mod, func, expr.orelse, depth - 1, seen))
        if isinstance(expr, ast.Name):
            return self.name(mod, func, expr, depth, seen, self.strings)
        return {None}

    def paths(self, mod: F.Module, func: F.Func | None, expr: ast.expr, depth: int, seen: frozenset[tuple[Key, str]]
              ) -> set[Path | None]:
        if depth <= 0:
            return {None}
        if isinstance(expr, ast.Name):
            return self.name(mod, func, expr, depth, seen, self.paths)
        if isinstance(expr, ast.IfExp):
            return (self.paths(mod, func, expr.body, depth - 1, seen)
                    | self.paths(mod, func, expr.orelse, depth - 1, seen))
        if not isinstance(expr, ast.Call):
            return {None}
        if mod.aliases.resolve(expr.func) == "argparse.ArgumentParser":
            return {()}
        if isinstance(expr.func, ast.Attribute):
            if expr.func.attr == "add_subparsers":
                return self.paths(mod, func, expr.func.value, depth - 1, seen)
            if expr.func.attr == "add_parser" and expr.args:
                base = self.paths(mod, func, expr.func.value, depth - 1, seen)
                words = self.strings(mod, func, expr.args[0], depth - 1, seen)
                return {None if b is None or w is None else (*b, w) for b in base for w in words}
        return {None}

    def name(self, mod: F.Module, func: F.Func | None, node: ast.Name, depth: int, seen: frozenset[tuple[Key, str]],
             value: Callable[..., set]) -> set:
        """What a name holds: its assignments (see :meth:`reads`), the literal elements of the loop that binds it, the
        arguments of the calls of its function when it is a parameter, or the module constant of that name."""
        scope = func
        while scope is not None and not (node.id in scope.params or any(
                node.id in names for names in (scope.assigns, scope.loops, scope.unpacks, scope.opaque, scope.withs,
                                               scope.key_loops))):
            scope = scope.parent
        if scope is None:
            const = mod.consts.get(node.id)
            return value(mod, None, const, depth - 1, seen) if const is not None else {None}
        token = (scope.key, node.id)
        if token in seen:
            return set()
        seen = seen | {token}
        home = self.program.modules[scope.module]
        found: set = set()
        assigned, parameter = self.reads(scope, node, scope is func)
        for rhs in assigned:
            found |= value(home, scope, rhs, depth - 1, seen)
        for iterable in scope.loops.get(node.id, []):
            found |= self._elements(home, scope, iterable, None, depth, seen, value)
        for index, iterable in scope.unpacks.get(node.id, []):
            found |= self._elements(home, scope, iterable, index, depth, seen, value)
        if parameter and node.id in scope.params:
            found |= self.arguments(scope, node.id, depth, seen, value)
        if node.id in scope.withs or node.id in scope.key_loops or (node.id in scope.opaque
                                                                     and node.id not in scope.unpacks):
            found.add(None)  # bound by `with`, an unpacking, `except`, a walrus or a mapping's keys
        return found or {None}

    def _elements(self, mod: F.Module, scope: F.Func, iterable: ast.expr, index: int | None, depth: int,
                  seen: frozenset[tuple[Key, str]], value: Callable[..., set]) -> set:
        """The values a loop variable takes over a literal tuple or list (``index`` picks the element of each row when
        the loop unpacks)."""
        if not isinstance(iterable, (ast.Tuple, ast.List)):
            return {None}
        out: set = set()
        for element in iterable.elts:
            if index is None:
                out |= value(mod, scope, element, depth - 1, seen)
            elif isinstance(element, (ast.Tuple, ast.List)) and index < len(element.elts):
                out |= value(mod, scope, element.elts[index], depth - 1, seen)
            else:
                out.add(None)
        return out

    def arguments(self, scope: F.Func, name: str, depth: int, seen: frozenset[tuple[Key, str]],
                  value: Callable[..., set]) -> set:
        """What a parameter holds: the argument of every static call of the function (a call that leaves it out
        gives the default). A function nothing calls, or called from more places than the program reads, is not
        read."""
        sites = self.program.callers.get(scope.key, [])
        if not sites or len(sites) > F.CALLERS:
            return {None}
        out: set = set()
        for caller, caller_mod, call in sites:
            argument = F._argument(scope, name, call)
            if argument is not None:
                out |= value(caller_mod, caller, argument, depth - 1, seen)
            elif name in scope.defaults:
                out |= value(self.program.modules[scope.module], None, scope.defaults[name], depth - 1, seen)
            else:
                out.add(None)
        return out


def registrations(program: F.Program) -> list[Registration]:
    """Every ``set_defaults(handler=...)`` of the program, with the command paths its parser spells."""
    reader = _Reader(program)
    out: list[Registration] = []
    for mod in sorted(program.modules.values(), key=lambda m: m.name):
        scopes: list[tuple[F.Func | None, list[ast.Call]]] = [(None, mod.module_calls)]
        scopes += [(f, f.calls) for f in mod.funcs.values()]
        for func, calls in scopes:
            for call in calls:
                if not (isinstance(call.func, ast.Attribute) and call.func.attr == "set_defaults"):
                    continue
                for kw in call.keywords:
                    if kw.arg != "handler":
                        continue
                    found = reader.paths(mod, func, call.func.value, DEPTH, frozenset())
                    out.append(Registration((mod.name, func.qual if func else ""), call.lineno,
                                            tuple(sorted(p for p in found if p is not None)), None in found,
                                            tuple(sorted(_handlers(program, mod, func, kw.value)))))
    return sorted(out)


def _handlers(program: F.Program, mod: F.Module, func: F.Func | None, value: ast.expr) -> set[Key]:
    """The functions a handler expression names: a lambda is a function of its own; anything else, the functions its
    names and attributes resolve to."""
    if isinstance(value, ast.Lambda) and id(value) in mod.handlers:
        return {mod.handlers[id(value)].key}
    found: set[Key] = set()
    for node in ast.walk(value):
        if isinstance(node, (ast.Name, ast.Attribute)):
            target = program.target(mod, func, node)
            if target is not None:
                found.add(target.key)
    return found


def cut_of(program: F.Program, role_of: Callable[[Path], str]) -> Cut:
    """The handlers of each role: a registration's handlers go to the role of every command path it spells, and a
    registration that also spells a path this reading cannot read has them undecided, under the function that registers
    them."""
    regs = registrations(program)
    handlers: dict[str, set[Key]] = defaultdict(set)
    undecided: dict[Key, set[Key]] = defaultdict(set)
    for r in regs:
        for path in r.paths:
            handlers[role_of(path)].update(r.handlers)
        if r.unread or not r.paths:
            undecided[r.registrar].update(r.handlers)
    return Cut(regs, dict(handlers), dict(undecided))
