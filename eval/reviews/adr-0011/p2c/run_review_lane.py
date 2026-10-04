"""Run the requested pytest command using this copy's venv, without visible Windows consoles."""
import subprocess
import sys
from pathlib import Path

import aew
import pytest

root = Path(__file__).resolve().parent
assert Path(aew.__file__).resolve().is_relative_to(root / 'src'), aew.__file__
assert Path(sys.executable).resolve().is_relative_to(root / '.venv'), sys.executable
if sys.platform == 'win32':
    original_popen = subprocess.Popen

    def hidden_popen(*args, **kwargs):
        kwargs['creationflags'] = kwargs.get('creationflags', 0) | subprocess.CREATE_NO_WINDOW
        return original_popen(*args, **kwargs)

    subprocess.Popen = hidden_popen

print('Review source:', aew.__file__, flush=True)
print('Review interpreter:', sys.executable, flush=True)
print('Pytest arguments:', sys.argv[1:], flush=True)
raise SystemExit(pytest.main(sys.argv[1:]))
