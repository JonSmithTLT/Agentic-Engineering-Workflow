"""Read-only Git commands; check every archived tracked byte without touching the main checkout."""
import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
metadata=json.loads((ROOT/'review-metadata.json').read_text())
main=ROOT.parents[1]/'Agentic-Engineering-Workflow'
archive=subprocess.run(['git','archive','--format=tar',metadata['target']],cwd=main,
                       creationflags=subprocess.CREATE_NO_WINDOW,capture_output=True,check=True).stdout
checked=0
with tarfile.open(fileobj=io.BytesIO(archive),mode='r:') as tar:
    for member in tar.getmembers():
        if not member.isfile():
            continue
        expected=tar.extractfile(member).read()
        actual=(ROOT/member.name).read_bytes()
        assert actual==expected,member.name
        checked+=1
pin=subprocess.run(['git','diff','--name-only',metadata['baseline'],metadata['target'],'--',
                    'docs/aew-knowledge-contract-v0.4.md','docs/agent-engineering-workflow-design-v0.7.md',
                    'docs/schemas'],cwd=main,creationflags=subprocess.CREATE_NO_WINDOW,
                    capture_output=True,text=True,check=True)
assert not pin.stdout.strip(),pin.stdout
result={'target':metadata['target'],'tracked_files_byte_verified':checked,
        'frozen_contract_and_workflow_changes':pin.stdout.strip()}
(ROOT/'review-source-verification.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
