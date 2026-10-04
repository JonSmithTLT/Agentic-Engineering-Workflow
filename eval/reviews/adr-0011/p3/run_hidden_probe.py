import runpy
import subprocess
import sys
from pathlib import Path
import aew
root=Path(__file__).resolve().parent
assert Path(aew.__file__).resolve().is_relative_to(root/'src')
assert Path(sys.executable).resolve().is_relative_to(root/'.venv')
if sys.platform=='win32':
    original=subprocess.Popen
    def hidden(*args,**kw):
        kw['creationflags']=kw.get('creationflags',0)|subprocess.CREATE_NO_WINDOW
        return original(*args,**kw)
    subprocess.Popen=hidden
script=sys.argv[1]
sys.argv=sys.argv[1:]
runpy.run_path(script,run_name='__main__')
