import json
import os
import subprocess
import sys
import time
from pathlib import Path
root=Path(__file__).resolve().parent
assert sys.platform=='win32'
label=sys.argv[1]
args=sys.argv[2:]
python=root/'.venv/Scripts/python.exe'
assert python.exists()
started=time.time()
with (root/(label+'.log')).open('w',encoding='utf-8') as out, (root/(label+'.stderr')).open('w',encoding='utf-8') as err:
 p=subprocess.Popen([str(python),*args],cwd=root,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
 code=p.wait()
(root/(label+'.result.json')).write_text(json.dumps({'args':args,'returncode':code,'elapsed_seconds':time.time()-started},indent=2)+'\n',encoding='utf-8')
print(label,code,round(time.time()-started,2),flush=True)
raise SystemExit(code)
