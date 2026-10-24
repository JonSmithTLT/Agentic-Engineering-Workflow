"""STG-11 authority-critical fixtures: WIS-01a, the store's group (wis-issuer-r9/WIS-ISSUER-PROFILE.md), stage revision 4.

Usage: python -I -B verify_store_group.py [--write]   (standard library only)

Amendment 1, A3: fixtures for the authority-critical rule only. The rule is one predicate, "the store's group is private
to the operator", stated over the group's ID in every source the host resolves (SG1-1). Two parties apply it, the store
writers and the qualifier, each from its own inputs: the host's listing and root's group record, and nothing of their own
(SG1-3). A signal in root's record shows privacy only for the IDs it covers, and the record names the group part 1 selects
(C1-1). The store writers' group and modes (D-CS1-10 and D-CS1-11 as STG-11 amends them) are bounded from above by WIS-00
at every migration step (SG1-2), and depend on every running store writer (SG1-5). A writer migrates when the control
file's group or mode differs from the target (D-CS1-1 as extended, C1-2), at its open and before every commit (C2-1).
The model knows every source, so it can
say what the kernel would grant; the parties see only what can be listed. Host facts are WIS-Q02's to measure; this is a
labelled reference model of the rule, not an oracle. Its user-private group is always a local entry; a directory-served
one is a host fact for WIS-Q02.
--write regenerates store-group-cases.json; a normal run requires it unchanged.
"""
import copy, json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OWNER_ONLY = (0o600, 0o700)
GROUP_READ = (0o640, 0o750)  # also WIS-00's upper bound: at most this, for files and directories
CONTROL = 'state/control.yaml'
N = 0; OUT = {}


def check(name, cond, detail=''):
    global N; N += 1
    if not cond:
        raise AssertionError(name + (': ' + detail if detail else ''))


def show(x):
    """JSON-friendly form: tuples and sets as lists (modes stay integers)."""
    if isinstance(x, dict):
        return {str(k): show(v) for k, v in x.items()}
    if isinstance(x, (list, tuple, set)):
        return [show(v) for v in (sorted(x) if isinstance(x, set) else x)]
    return x


def record(name, value):
    OUT[name] = show(value)
    return value


# ---------------------------------------------------------------- what the kernel grants (the model sees every source)
def holders(h, gid):
    """Every account the kernel lets act with gid: as its primary group, or as a listed member of any entry with that ID."""
    out = {a['name'] for a in h['accounts'] if a['primary'] == gid}
    for g in h['groups']:
        if g['gid'] == gid:
            out |= set(g['members'])
    return out


def primary_of(h):
    return next(a['primary'] for a in h['accounts'] if a['name'] == h['operator'])


# ---------------------------------------------------------------- the parties' inputs (WIS-01a part 4)
def listed(h):
    """What any party can list: the entries of the sources that can be listed. The operator's own entry is always seen."""
    ok = {s for s, can in h['sources'].items() if can}
    return [g for g in h['groups'] if g['src'] in ok], [a for a in h['accounts'] if a['src'] in ok or a['name'] == h['operator']]


def writer_inputs(h):
    return listed(h), h['record']  # a store writer's inputs: no signal of its own


def qualifier_inputs(h):
    return listed(h), h['record']  # the qualifier's inputs: the same record


# ---------------------------------------------------------------- the rule (WIS-01a parts 1 to 4)
def wis01a(h, listing, record):
    """Returns (gid, kind, None) where the store's group is private to the operator, else (None, None, reason)."""
    groups, accounts = listing
    signals = (record or {}).get('signals', {})
    unlistable = sorted(s for s, can in h['sources'].items() if not can)

    def alone(gid, name, members):
        """Part 2 over the sources that can be listed, and part 3 for each source that cannot."""
        entries = [g for g in groups if g['gid'] == gid]
        if not entries:
            return 'NO_ENTRY'
        if any(g['name'] != name for g in entries):
            return 'ID_HELD_ELSEWHERE'  # another group entry has the ID (SG1-1)
        if any(g['members'] != members for g in entries):
            return 'MEMBERS'
        if any(a['primary'] == gid and a['name'] != h['operator'] for a in accounts):
            return 'PRIMARY_ELSEWHERE'
        if any(gid not in signals.get(s, {}).get('ids', ()) for s in unlistable):
            return 'UNLISTABLE_NO_SIGNAL'  # only root's record speaks for a source that cannot be listed, and only for the IDs it covers (C1-1)
        return None

    primary = primary_of(h)
    named = (record or {}).get('group')  # root's group record names the store's group (part 4)
    if alone(primary, h['operator'], []) is None:
        if named is not None and named['gid'] != primary:
            return None, None, 'RECORD_NAMES_OTHER'  # the record names a group other than the one part 1 selects (C1-1)
        return primary, 'USER_PRIVATE', None  # a local AEW group is not used here, even if one exists
    aew = named
    if aew is None:
        return None, None, 'NO_PRIVATE_GROUP'
    local = [g for g in groups if g['gid'] == aew['gid'] and g['src'] == 'files']
    if not local or local[0]['name'] != aew['name']:
        return None, None, 'NOT_LOCAL'  # absent, in a directory, or contradicting root's record
    why = alone(aew['gid'], aew['name'], [h['operator']])
    if why:
        return None, None, why
    return aew['gid'], 'LOCAL_AEW', None


def writer_private(h):
    return wis01a(h, *writer_inputs(h))


def qualifier_private(h):
    return wis01a(h, *qualifier_inputs(h))


# ---------------------------------------------------------------- the store writers (D-CS1-10, D-CS1-11 as amended)
def publish(h, w):
    """The group and modes writer w publishes. The same for every store writer: it looks at every running one (SG1-5)."""
    assert w['running']
    gid, _, _ = writer_private(h)
    if gid is not None and all(gid in x['holds'] for x in h['writers'] if x['running']):
        return gid, GROUP_READ
    return primary_of(h), OWNER_ONLY


def migrate(h, w, state):
    """Writer w's migration: each path to what publish allows, re-grouping and re-moding, the control file last (D-CS1-1).
    Returns the state after each step, so every intermediate state can be checked (SG1-2)."""
    gid, modes = publish(h, w)
    cur, steps = dict(state), []
    for p in sorted(state, key=lambda p: p == CONTROL):
        g, m = cur[p]
        want = modes[1] if p.endswith('/') else modes[0]
        if want & 0o070:
            ops = [('grp', gid), ('mode', want)]  # going group-readable: re-group first
        else:
            ops = [('mode', want), ('grp', gid)]  # going owner-only: re-mode first
        for op, v in ops:
            g, m = (v, m) if op == 'grp' else (g, v)
            cur[p] = (g, m)
            steps.append((p, dict(cur)))
    return steps


def open_session(h, w, state):
    """D-CS1-1 as extended (C1-2): at a writer's open, under the control lock, the record is the control file's group and mode. If
    either differs from what publish allows now, the whole store migrates: a change of group alone, at the same modes, is a migration."""
    gid, modes = publish(h, w)
    if state[CONTROL] == (gid, modes[0]):
        return dict(state), []  # already at the target: nothing to walk
    steps = migrate(h, w, state)
    return steps[-1][1], steps


def commit(h, w, state, path):
    """D-CS1-1 as revision 4 extends it (C2-1): before every commit, not only at open, under the control lock, the record is compared
    with what publish allows now, and the store migrates first if they differ. The commit then publishes its log record, and the
    control file last, at the target. So no commit publishes the control file at a group or mode the rest of the store does not carry."""
    state, steps = open_session(h, w, state)  # the same comparison as at open
    gid, modes = publish(h, w)
    state = dict(state)
    state[path] = (gid, modes[0])
    state[CONTROL] = (gid, modes[0])
    return state, steps


def session(h, w, state):
    steps = migrate(h, w, state)
    return steps[-1][1] if steps else dict(state)


def grants(state):
    """What a store state grants beyond its owner: (path, class, group, bits)."""
    out = set()
    for p, (g, m) in state.items():
        if m & 0o070:
            out.add((p, 'group', g, m & 0o070))
        if m & 0o007:
            out.add((p, 'other', None, m & 0o007))
    return out


def readers(h, state):
    """Who besides the operator the kernel lets read some store path: the holders of a path's group where it has group read."""
    out = set()
    for g, m in state.values():
        if m & 0o040:
            out |= holders(h, g) - {h['operator']}
        if m & 0o004:
            out.add('others')
    return out


def within_bound(state):
    """WIS-00's upper bound (SG1-2): at most 0640 for files and 0750 for directories; nothing to others."""
    for p, (g, m) in state.items():
        bound = GROUP_READ[1] if p.endswith('/') else GROUP_READ[0]
        if m & ~bound:
            return False
    return True


def doctor(h):
    gid, kind, why = writer_private(h)
    lacking = [w['name'] for w in h['writers'] if w['running'] and gid is not None and gid not in w['holds']]
    return {'store_group': gid, 'kind': kind, 'reason': why, 'writers_lacking': lacking}


# ---------------------------------------------------------------- WIS-Q02's group rows (revision 7)
def qualifiable(h, state):
    gid, kind, why = qualifier_private(h)
    if gid is None:
        return False, why
    if set(h['issuer_holds']) - {h['issuer_own']} != {gid}:
        return False, 'ISSUER_GROUPS'  # what the issuer's process holds, from inside the unit (SG1-9)
    if any(gid not in w['holds'] for w in h['writers'] if w['running']):
        return False, 'WRITER_LACKS_GROUP'
    if not within_bound(state):
        return False, 'STORE_MODES'
    for p, (g, m) in state.items():
        if g != gid or not m & 0o040 or (p.endswith('/') and not m & 0o010):
            return False, 'STORE_NOT_CARRIED'
    if kind == 'LOCAL_AEW' and any(g == gid for g in h['outside_files'].values()):
        return False, 'OUTSIDE_CARRIES'  # part 6, at qualification; a user-private group marks the operator's files, and the view bounds it
    return True, None


# ---------------------------------------------------------------- the synthetic hosts
def login(*extra):
    return {'name': 'login', 'running': True, 'holds': [1000, 100, *extra]}


def host(primary='oper', primary_members=(), aew=None, aew_members=('oper',), aew_local=True, directory=True, signal=None,
         covers=range(900, 1000), record='default', dir_groups=(), others=(), writers=None):
    groups = [{'src': 'files', 'name': 'oper', 'gid': 1000, 'members': list(primary_members)},
              {'src': 'directory', 'name': 'users', 'gid': 100, 'members': ['alice', 'bob']}]
    accounts = [{'src': 'files', 'name': 'oper', 'primary': 1000 if primary == 'oper' else 100},
                {'src': 'directory', 'name': 'alice', 'primary': 100}, {'src': 'directory', 'name': 'bob', 'primary': 100}]
    accounts += [{'src': 'files', 'name': n, 'primary': gid} for n, gid in others]
    groups += [{'src': 'directory', 'name': n, 'gid': gid, 'members': list(m)} for n, gid, m in dir_groups]
    if aew is not None:
        groups.append({'src': 'files' if aew_local else 'directory', 'name': 'aew-oper', 'gid': aew, 'members': list(aew_members)})
    if record == 'default':  # root's group record names the local AEW group, where root made one
        record = {'group': {'name': 'aew-oper', 'gid': aew}} if aew is not None else None
    if signal:  # a signal covers the IDs it names, and no others (C1-1)
        record = dict(record or {}, signals={'directory': {'text': signal, 'ids': list(covers)}})
    h = {'operator': 'oper', 'sources': {'files': True, 'directory': directory}, 'groups': groups, 'accounts': accounts,
         'record': record, 'convention': None, 'outside_files': {'/home/oper/notes.txt': 1000 if primary == 'oper' else 100},
         'issuer_own': 61000, 'writers': writers or [login(*([aew] if aew is not None else []))]}
    sg = writer_private(h)[0]
    h['issuer_holds'] = [61000] + ([sg] if sg is not None else [])  # root's drop-in names the store's group (WIS-01)
    return h


def fresh(h):
    """A store as it is today: owner-only, under the operator's primary group."""
    p = primary_of(h)
    return {'state/': (p, 0o700), 'state/log/000001.yaml': (p, 0o600), CONTROL: (p, 0o600)}


def outcome(h, w=None):
    w = w or h['writers'][0]
    gid, kind, reason = writer_private(h)
    state = session(h, w, fresh(h))
    ok, why = qualifiable(h, state)
    return {'store_group': gid, 'kind': kind, 'reason': reason, 'publish': publish(h, w), 'qualifiable': ok, 'why': why,
            'doctor': doctor(h)}


HOSTS = {}  # every host below, for the agreement and safety sweeps


def case(name, h, w=None):
    HOSTS[name] = h
    return record(name, outcome(h, w))


# ---------------------------------------------------------------- P: the private group, by host
r = case('P1 a user-private primary group', host())
check('P1 the user-private primary group is the store\'s group, private; files group-readable (revision 5 unchanged)',
      r['store_group'] == 1000 and r['kind'] == 'USER_PRIVATE' and r['publish'] == (1000, GROUP_READ) and r['qualifiable'], str(r))
r = case('P2 a shared primary group, no AEW group', host(primary='users'))
check('P2 a shared primary group and no AEW group: no private group; owner-only; not qualifiable (D-CS1-11)',
      r['store_group'] is None and r['reason'] == 'NO_PRIVATE_GROUP' and r['publish'] == (100, OWNER_ONLY) and not r['qualifiable'], str(r))
r = case('P3 a shared primary group with a local AEW group', host(primary='users', aew=990))
check('P3 a shared primary group with a local AEW group, the operator its only member: private; files carry it, group-readable',
      r['store_group'] == 990 and r['kind'] == 'LOCAL_AEW' and r['publish'] == (990, GROUP_READ) and r['qualifiable'], str(r))
r = case('P4 a user-private primary group, with an AEW group too', host(aew=990, record={'group': {'name': 'oper', 'gid': 1000}}))
check('P4 where the primary group is user-private, it stays the store\'s group; the AEW group is not used (the operator\'s words)',
      r['store_group'] == 1000 and r['publish'][0] == 1000, str(r))
r = case('P4b a user-private primary group, with root\'s record naming the AEW group', host(aew=990))
check('P4b C1-1 the record names a group other than the one part 1 selects: not private, owner-only',
      r['store_group'] is None and r['reason'] == 'RECORD_NAMES_OTHER' and r['publish'][1] == OWNER_ONLY, str(r))
r = case('P5 a user-private-looking primary group with a listed member', host(primary_members=('alice',)))
check('P5 a primary group with a listed member is not user-private: with no AEW group, owner-only',
      r['store_group'] is None and r['publish'][1] == OWNER_ONLY, str(r))
r = case('P5b the same, with a local AEW group', host(primary_members=('alice',), aew=990))
check('P5b then the AEW group is the store\'s group', r['store_group'] == 990 and r['qualifiable'], str(r))
h = host(); h['groups'][0]['name'] = 'devs'
r = case('P6 a primary group not named for the operator', h)
check('P6 a primary group not named for the operator is not user-private (the brief\'s CB-08 definition): owner-only',
      r['store_group'] is None and r['publish'][1] == OWNER_ONLY, str(r))

# ---------------------------------------------------------------- A: what makes a group not private
for label, kw, reason in [('a second member', {'aew_members': ('oper', 'alice')}, 'MEMBERS'),
                          ('no member', {'aew_members': ()}, 'MEMBERS'),
                          ('a directory group, not local', {'aew_local': False}, 'NOT_LOCAL'),
                          ('another account\'s primary group', {'others': (('carol', 990),)}, 'PRIMARY_ELSEWHERE'),
                          ('an unlistable directory and no signal', {'directory': False}, 'UNLISTABLE_NO_SIGNAL')]:
    r = case(f'A1 an AEW group with {label}', host(primary='users', aew=990, **kw))
    check(f'A1 an AEW group with {label} is not private: {reason}; owner-only, not qualifiable', r['store_group'] is None
          and r['reason'] == reason and r['publish'] == (100, OWNER_ONLY) and not r['qualifiable'], str(r))
h = host(primary='users', aew=990); h['record'] = None
r = case('A1 an AEW group root never named', h)
check('A1 a local AEW group with no root\'s group record is not used (part 4)', r['store_group'] is None and r['reason'] == 'NO_PRIVATE_GROUP', str(r))
h = host(primary='users', aew=990); h['record']['group']['name'] = 'aew-old'
r = case('A1 a listing that contradicts root\'s record', h)
check('A1 what the host lists now contradicts root\'s record: not private (part 4)', r['store_group'] is None and r['reason'] == 'NOT_LOCAL', str(r))
r = case('A2 the work host: an unlistable directory, with root\'s recorded signal',
         host(primary='users', aew=990, directory=False, signal='the site reserves gid 900-999 for local groups'))
check('A2 an unlistable directory with root\'s recorded signal: private, and qualifiable (the amendment\'s outcome is met)',
      r['store_group'] == 990 and r['publish'] == (990, GROUP_READ) and r['qualifiable'], str(r))
r = case('A3 a user-private primary group in an unlistable directory, no signal', host(directory=False))
check('A3 a user-private primary group needs the same: unlistable and no signal means not private', r['store_group'] is None, str(r))

# ---------------------------------------------------------------- SG1-1: the ID, in every source (the reviewer's probes A and B)
r = case('SG1-1 probe A: a directory group with the AEW group\'s ID, listable',
         host(primary='users', aew=990, dir_groups=(('proj-x', 990, ('alice', 'bob')),)))
check('SG1-1 probe A: another group entry with the store group\'s ID makes it not private; owner-only',
      r['store_group'] is None and r['reason'] == 'ID_HELD_ELSEWHERE' and r['publish'] == (100, OWNER_ONLY) and not r['qualifiable'], str(r))
r = case('SG1-1 probe A: the same, unlistable, no signal',
         host(primary='users', aew=990, directory=False, dir_groups=(('proj-x', 990, ('alice', 'bob')),)))
check('SG1-1 probe A unlistable: without root\'s signal, not private', r['store_group'] is None and r['reason'] == 'UNLISTABLE_NO_SIGNAL', str(r))
r = case('SG1-1 probe B: a directory group with the user-private ID, listable', host(dir_groups=(('carol', 1000, ('carol',)),)))
check('SG1-1 probe B: a primary group whose ID another holds is not user-private; with no AEW group, owner-only (narrows revision 5, fails closed)',
      r['store_group'] is None and r['publish'][1] == OWNER_ONLY, str(r))
r = case('SG1-1 probe B with a local AEW group', host(aew=990, dir_groups=(('carol', 1000, ('carol',)),)))
check('SG1-1 probe B with a local AEW group: the AEW group is the store\'s group (the operator\'s words)',
      r['store_group'] == 990 and r['kind'] == 'LOCAL_AEW' and r['qualifiable'], str(r))
h = host(primary='users', aew=990, directory=False, signal='the site reserves gid 900-999 for local groups',
         dir_groups=(('proj-x', 990, ('alice', 'bob')),))
h['false_signal'] = True
r = case('SG1-1 residual: root\'s signal is false', h)
check('SG1-1 residual: a false signal in root\'s record is root\'s and the site\'s; no AEW party can see it (stated, not bound)',
      r['store_group'] == 990 and holders(h, 990) == {'alice', 'bob', 'oper'}, str(r))

# ---------------------------------------------------------------- C1-1: a signal covers only its IDs (the check's probes B5, B6)
SIG = 'the site reserves gid 900-999 for local groups'
h = host(aew=990, directory=False, signal=SIG, dir_groups=(('old-team', 1000, ('carol',)),))
r = case('C1-1 probe B5: a user-private ID held in a directory that cannot be listed, a true signal for 900-999', h)
check('C1-1 B5 the signal does not cover 1000, so the user-private group is not private; the store goes to the AEW group',
      r['store_group'] == 990 and r['kind'] == 'LOCAL_AEW' and r['publish'] == (990, GROUP_READ) and holders(h, 990) == {'oper'}, str(r))
h = host(directory=False, signal=SIG, dir_groups=(('old-team', 1000, ('carol',)),))
r = case('C1-1 probe B6: the same, no AEW group, only the signal', h)
check('C1-1 B6 with no AEW group: no private group, owner-only (carol reads nothing)',
      r['store_group'] is None and r['reason'] == 'NO_PRIVATE_GROUP' and r['publish'][1] == OWNER_ONLY, str(r))
r = case('C1-1 a signal that covers the user-private ID', host(directory=False, signal='the directory serves no gid below 60000', covers=[1000]))
check('C1-1 a true signal that covers the user-private ID makes it private where the directory cannot be listed',
      r['store_group'] == 1000 and r['kind'] == 'USER_PRIVATE' and r['qualifiable'], str(r))

# ---------------------------------------------------------------- SG1-3: one determination, two parties (probe D)
h = host(directory=False); h['convention'] = {'signals': {'directory': {'text': 'the user-private-group convention', 'ids': [1000]}}}
r = case('SG1-3 a writer\'s own signal is not a determination', h)
check('SG1-3 with no signal in root\'s record, a writer that has a convention of its own still publishes owner-only',
      r['store_group'] is None and r['publish'][1] == OWNER_ONLY, str(r))
check('SG1-3 (a) the work host: root\'s recorded signal reaches the store writers, so the outcome is met',
      writer_private(HOSTS['A2 the work host: an unlistable directory, with root\'s recorded signal'])[0] == 990)

# ---------------------------------------------------------------- SG1-2: WIS-00's upper bound, and the migration's every step
for label, state in [('a file at 0644', {'state/': (990, 0o750), 'state/log/000001.yaml': (990, 0o640), CONTROL: (990, 0o644)}),
                     ('a directory at 0755', {'state/': (990, 0o755), 'state/log/000001.yaml': (990, 0o640), CONTROL: (990, 0o640)}),
                     ('a group-writable file', {'state/': (990, 0o750), 'state/log/000001.yaml': (990, 0o660), CONTROL: (990, 0o640)})]:
    ok, why = qualifiable(host(primary='users', aew=990), state)
    check(f'SG1-2 a store writer bug, {label}: WIS-Q02 fails on the bound', not ok and why == 'STORE_MODES', why)
state = {'state/': (100, 0o750), 'state/log/000001.yaml': (990, 0o640), CONTROL: (990, 0o640)}
ok, why = qualifiable(host(primary='users', aew=990), state)
check('SG1-2 a directory left on the shared group: WIS-Q02 fails (every file and directory carries the store\'s group)',
      not ok and why == 'STORE_NOT_CARRIED', why)
h = host(primary='users', aew=990)
up = migrate(h, h['writers'][0], fresh(h))
h2 = copy.deepcopy(h); h2['groups'][-1]['members'].append('alice')  # root adds a member later (the residual risk)
start = up[-1][1]
down = migrate(h2, h2['writers'][0], start)
record('SG1-2 the migration up, step by step', [s for _, s in up])
record('SG1-2 the migration down after root adds a member', [s for _, s in down])
check('SG1-2 up: no step grants anything the end state does not, and the end is within the bound',
      all(grants(s) <= grants(up[-1][1]) for _, s in up) and within_bound(up[-1][1]))
check('SG1-2 down: no step grants anything the start does not, and the end is owner-only',
      all(grants(s) <= grants(start) for _, s in down) and grants(down[-1][1]) == set())
check('D-CS1-1 the control file is the last path re-grouped and re-moded, in both directions',
      up[-1][0] == CONTROL and up[-2][0] == CONTROL and down[-1][0] == CONTROL and down[-2][0] == CONTROL)
back = migrate(h, h['writers'][0], down[-1][1])
check('W3 a later session, with the group private again, brings the store back', back[-1][1] == start, str(back[-1][1]))

# ---------------------------------------------------------------- C1-2: a change of group alone is a migration (D-CS1-1 extended)
h0 = host(record={'group': {'name': 'oper', 'gid': 1000}})
upg = session(h0, h0['writers'][0], fresh(h0))  # a revision-5 store: the user-private group, group-readable
h1 = host(aew=990, dir_groups=(('old-team', 1000, ('carol',)),))  # the directory gives 1000 to carol; root names the AEW group
moved, steps = open_session(h1, h1['writers'][0], upg)
record('C1-2 the sideways move from the user-private group to the AEW group, at equal modes', {'from': upg, 'to': moved, 'steps': len(steps)})
check('C1-2 at equal modes the open still migrates: every path is re-grouped to 990, and nothing stays under 1000 for carol',
      all(m in GROUP_READ for _, m in upg.values()) and steps and all(g == 990 for g, _ in moved.values()), str(moved))
check('C1-2 no step of the move grants anything that neither its start nor its end grants',
      all(grants(s) <= grants(upg) | grants(moved) for _, s in steps))
again, steps2 = open_session(h1, h1['writers'][0], moved)
check('C1-2 a store already at the target group and mode is not walked again', steps2 == [] and again == moved)

# ---------------------------------------------------------------- C2-1: the record is compared before every commit (D-CS1-1, revision 4)
hw = host(aew=990, record={'group': {'name': 'oper', 'gid': 1000}})  # a user-private host where root has also made aew-oper
w = hw['writers'][0]  # a writer that holds aew-oper (990) and the user-private group
s, _ = open_session(hw, w, fresh(hw))  # a revision-5 store on the user-private group, group-readable
check('C2-1 the store starts on the user-private group, group-readable', all(g == 1000 for g, _ in s.values()) and s[CONTROL] == (1000, 0o640), str(s))
s, _ = commit(hw, w, s, 'state/log/000002.yaml')
for label, later in [('M1 the directory gives 1000 to carol, and root names the AEW group',
                      host(aew=990, dir_groups=(('old-team', 1000, ('carol',)),))),
                     ('M2 the same move before root re-names: the rule says owner-only, the group unchanged',
                      host(aew=990, record={'group': {'name': 'oper', 'gid': 1000}}, dir_groups=(('old-team', 1000, ('carol',)),)))]:
    after, steps = commit(later, w, s, 'state/log/000003.yaml')  # the change lands while the writer is open
    record(f'C2-1 {label}', {'before': s, 'after': after, 'steps': len(steps)})
    check(f'C2-1 {label}: the next commit migrates first, so no store path stays readable to carol',
          steps and readers(later, after) == set(), str(after))
    check(f'C2-1 {label}: no step grants anything that neither its start nor its end grants',
          all(grants(x) <= grants(s) | grants(after) for _, x in steps))
    again, steps2 = open_session(later, w, after)
    check(f'C2-1 {label}: the record is then right, so the next open walks nothing and still exposes no one',
          steps2 == [] and readers(later, again) == set(), str(again))
h = host(primary='users', aew=990)
s, _ = open_session(h, h['writers'][0], fresh(h))
s, _ = commit(h, h['writers'][0], s, 'state/log/000002.yaml')
h2 = copy.deepcopy(h); h2['groups'][-1]['members'].append('alice')  # root adds a member while the writer is open
after, steps = commit(h2, h2['writers'][0], s, 'state/log/000003.yaml')
record('C2-1 M3 root adds alice to the AEW group while a writer is open', {'before': s, 'after': after, 'steps': len(steps)})
check('C2-1 M3 a member added while a writer is open: its next commit returns the whole store to owner-only (the stated residual\'s bound)',
      steps and readers(h2, after) == set() and all(m in OWNER_ONLY for _, m in after.values()), str(after))

# ---------------------------------------------------------------- C2-2: each half the answers state, pinned
h1b = host(aew=990, record={'group': {'name': 'oper', 'gid': 1000}}, dir_groups=(('old-team', 1000, ('carol',)),))
down, steps = open_session(h1b, h1b['writers'][0], upg)
check('C2-2 a change of mode alone, at the same group, is a migration at open too: every path owner-only, carol reads nothing',
      steps and all(g == 1000 and m in OWNER_ONLY for g, m in down.values()) and readers(h1b, down) == set(), str(down))
two = dict(upg); two['state/log/000002.yaml'] = upg['state/log/000001.yaml']
two = {p: two[p] for p in ['state/', 'state/log/000001.yaml', 'state/log/000002.yaml', CONTROL]}
walk = migrate(h1, h1['writers'][0], two)
cut = walk[[p for p, _ in walk].index('state/log/000002.yaml') - 1][1]  # interrupted: the first record moved, the second and the control file not
check('C2-2 the interrupted walk is set up as described', cut['state/log/000001.yaml'] == (990, 0o640)
      and cut['state/log/000002.yaml'] == (1000, 0o640) and cut[CONTROL] == (1000, 0o640), str(cut))
resumed, steps = open_session(h1, h1['writers'][0], cut)
check('C2-2 the record is the control file\'s, not a log record\'s: an interrupted walk is resumed at the next open, and carol reads nothing',
      steps and all(g == 990 for g, _ in resumed.values()) and readers(h1, resumed) == set(), str(resumed))
h = host(primary='users', aew=990, directory=False, signal=SIG)
h['sources']['nis'] = False; h['groups'].append({'src': 'nis', 'name': 'lab', 'gid': 990, 'members': ['carol']})
r = case('C2-2 two unlistable sources, a signal for one only', h)
check('C2-2 a signal covers only its own source: the second unlistable source has none, so not private, owner-only',
      r['store_group'] is None and r['reason'] == 'UNLISTABLE_NO_SIGNAL' and r['publish'][1] == OWNER_ONLY, str(r))

# ---------------------------------------------------------------- SG1-5: every running store writer (probe E)
old = {'name': 'broker', 'running': True, 'holds': [1000, 100]}  # began before root added the operator to the AEW group
h = host(primary='users', aew=990, writers=[login(990), old])
r = case('SG1-5 probe E: a login session and an older broker', h)
s = fresh(h)
seq = []
for w in [h['writers'][0], old, h['writers'][0], old]:
    s = session(h, w, s)
    seq.append(sorted(set(s.values())))
record('SG1-5 the store after alternating write sessions', seq)
check('SG1-5 while a running store writer lacks the group, every writer publishes owner-only: the store does not alternate',
      all(x == seq[0] for x in seq) and all(m in OWNER_ONLY for _, m in s.values()), str(seq))
check('SG1-5 and WIS-Q02 names the cause', r['why'] == 'WRITER_LACKS_GROUP' and not r['qualifiable'], str(r))
check('SG1-5 aew doctor names each running store writer whose credentials lack the group', r['doctor']['writers_lacking'] == ['broker'], str(r))
h2 = copy.deepcopy(h); h2['writers'][1]['holds'].append(990)  # the remedy: restart it
r = case('SG1-5 after the broker restarts', h2)
check('SG1-5 once every running store writer holds the group, the store is group-readable and qualifiable', r['qualifiable'], str(r))
h3 = copy.deepcopy(h); h3['writers'][1]['running'] = False
check('SG1-5 a store writer that is not running does not count', publish(h3, h3['writers'][0]) == (990, GROUP_READ))
cli = {'name': 'old-pane-cli', 'running': False, 'holds': [1000, 100]}  # an aew command from a multiplexer older than the group
h = host(primary='users', aew=990, writers=[login(990), cli])
s, seen = fresh(h), []
for runs in (False, True, False):
    cli['running'] = runs
    s = session(h, cli if runs else h['writers'][0], s)
    seen.append((runs, sorted(set(s.values())), doctor(h)['writers_lacking']))
record('SG1-5 residual: a short-lived command from an old session', seen)
check('SG1-5 residual (stated, fails closed): an old-session command flips the store to owner-only while it runs, and the next holding writer brings it back',
      seen[0][1] == [(990, 0o640), (990, 0o750)] and all(m in OWNER_ONLY for _, m in seen[1][1]) and seen[2][1] == seen[0][1], str(seen))
check('SG1-5 residual: doctor names it only while it runs, so the remedy covers every session older than the group',
      seen[1][2] == ['old-pane-cli'] and seen[0][2] == [] and seen[2][2] == [], str(seen))

# ---------------------------------------------------------------- SG1-4, SG1-6, SG1-9 and WIS-Q02's other rows
check('SG1-4 the gate\'s pass on a user-private host: its listed members are none, and it passes (probe C)',
      qualifiable(HOSTS['P1 a user-private primary group'], session(host(), host()['writers'][0], fresh(host()))) == (True, None))
h = host(primary='users', aew=990); h['outside_files']['/run/aew-oper.sock'] = 990
check('SG1-6 no file outside the store may carry a local AEW group, at qualification', qualifiable(h, session(h, h['writers'][0], fresh(h))) == (False, 'OUTSIDE_CARRIES'))
check('SG1-6 the store writers do not re-check part 6: membership alone exposes the store to no one new', publish(h, h['writers'][0]) == (990, GROUP_READ))
check('SG1-6 a user-private group marks the operator\'s own files as revision 5 had it; the issuer\'s view bounds what it reaches',
      host()['outside_files']['/home/oper/notes.txt'] == 1000 and outcome(host())['qualifiable'])
h = host(primary='users', aew=990); h['issuer_holds'] = [61000, 990, 50]
check('SG1-9 the issuer\'s process holds the store\'s group and no other but its own', qualifiable(h, session(h, h['writers'][0], fresh(h))) == (False, 'ISSUER_GROUPS'))
h = host(primary='users', aew=990); h['issuer_holds'] = [61000]
check('SG1-9 an issuer process without the store\'s group fails', qualifiable(h, session(h, h['writers'][0], fresh(h))) == (False, 'ISSUER_GROUPS'))
check('Q3 a qualifiable host passes every row', outcome(host(primary='users', aew=990))['qualifiable'])

# ---------------------------------------------------------------- sweeps over every host above
for name, h in HOSTS.items():
    check(f'SWEEP the two parties agree: {name}', writer_private(h) == qualifier_private(h))
    g, modes = publish(h, h['writers'][0])
    if modes == GROUP_READ and not h.get('false_signal'):
        check(f'SWEEP group-readable only where the kernel admits no one but the operator: {name}', holders(h, g) == {'oper'}, str(holders(h, g)))

cases = HERE / 'store-group-cases.json'
text = json.dumps({'status': 'generated by verify_store_group.py (STG-11 revision 4, A-27 revision 9); a labelled reference model, not an oracle',
                   'cases': OUT}, indent=1, sort_keys=True) + '\n'
if '--write' in sys.argv:
    cases.write_bytes(text.encode('utf-8'))
else:
    check('store-group-cases.json equals what the cases produce (regenerate with --write)', cases.exists() and cases.read_text(encoding='utf-8') == text)
print('PASS STG-11 store-group fixtures:', N, 'named checks')
