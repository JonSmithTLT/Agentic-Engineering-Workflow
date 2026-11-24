"""Replay the bounded, nonproduction experiment on actual two-parent trees; do not use as a CI policy."""

import subprocess
from unittest.mock import patch

import windows_selection as selector
from lanes import lane_of


def inspect(number, merge, total, expected_omissions):
    git = subprocess.check_output
    paths = git(['git', 'ls-tree', '-r', '--name-only', merge], text=True).splitlines()
    has_register = 'tests/flake-register.yaml' in paths

    def historical(argv, *args, **kwargs):
        # These early commits predate the register. Only the immutable historical replay supplies its empty form.
        if not has_register and argv[-2] == 'show' and argv[-1].endswith(':tests/flake-register.yaml'):
            return b'schema: aew/flake-register/v1\nentries: []\n'
        return git(argv, *args, **kwargs)

    inventory = selector.test_modules(dict.fromkeys(paths, ''))
    with patch.object(subprocess, 'check_output', side_effect=historical):
        omitted = selector.from_merge(merge, omit=True)
    assert len(inventory) == total and omitted == expected_omissions, omitted
    assert 'tests/integration/test_operator_autostart.py' in inventory - omitted
    print(f'#{number} {merge}: {len(inventory - omitted)}/{len(inventory)} retained; omitted {sorted(omitted)}; '
          f'historical register present = {has_register}', flush=True)


inspect(431, '54021c9dc755c83788287b71d74aec99a9eb128f', 156, set())
inspect(432, '2e03ae6807a3df6a8dcfb5125f9163e5db9fd2fd', 158, set())
inspect(499, '15c84eee53da12fee439d244b2fbf66f890589c2', 181, set())
assert lane_of('tests/unit/test_worker_stored_keys.py', []) == 'fast'
inspect(524, 'd97f7bb42614019b581096e8a71c05805fed8fb2', 183, selector.STORE_SUITES)
inspect(552, '4f3df0b3ded2f6a6c92765e52b704f2dafbe09e8', 186, set())
