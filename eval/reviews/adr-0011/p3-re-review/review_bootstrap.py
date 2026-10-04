import json
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
assert sys.platform == 'win32'
def run(argv, log):
    with (root/log).open('w', encoding='utf-8') as out:
        proc = subprocess.Popen(argv, cwd=root, stdout=out, stderr=subprocess.STDOUT,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        code = proc.wait()
    print(log, code, flush=True)
    if code:
        raise SystemExit(code)
gh = r'C:\Program Files\GitHub CLI\gh.exe'
run([gh, 'pr', 'view', '24', '--repo', 'JonSmithTLT/Agentic-Engineering-Workflow',
     '--json', 'headRefOid,baseRefOid,url,comments,statusCheckRollup'], 'review-pr.json')
pr = json.loads((root/'review-pr.json').read_text(encoding='utf-8'))
assert pr['headRefOid'] == '1911894bdc6e7126d31a9de362d792a9b7421fee', pr['headRefOid']
run([sys.executable, '-m', 'venv', str(root/'.venv')], 'review-venv.log')
site = root/'.venv/Lib/site-packages'
(site/'review_hidden_windows.py').write_text("import subprocess,sys\nif sys.platform=='win32':\n _original=subprocess.Popen\n def hidden(*args,**kw):\n  kw['creationflags']=kw.get('creationflags',0)|subprocess.CREATE_NO_WINDOW\n  return _original(*args,**kw)\n subprocess.Popen=hidden\n", encoding='utf-8')
(site/'review_hidden_windows.pth').write_text('import review_hidden_windows\n', encoding='utf-8')
run([str(root/'.venv/Scripts/python.exe'), '-m', 'pip', 'install', '-e', '.[dev,parallel]'], 'review-install.log')
