# Independent joint-wrapper review

Head: 041595cff23c0d90d81c5ac2abc89b2a7bb05149. Base: 50cd41be5b3bf050037e527b781de403c9f88e0b. Date: 2026-10-20.

This normal review covers the complete four-file delta: joint-mode host implementation, standalone tests, JOINT-WRAPPER.md and the preserved prior review. Read AGENTS.md, the testing strategy, the designer's shared JOINT-TEST-BRIEF.md and the implementation/docs diff. Contract boundary remains the adopted sealed v0.5.4; no contract or UI changes are part of this delta. No backend source, backend branches/private notes, other chats/people or actual backend port 4261 were accessed. Only this report was written.

## Exact-head CI observation

At 2026-10-20T19:54:29-04:00, local git rev-parse HEAD returned 041595cff23c0d90d81c5ac2abc89b2a7bb05149 and git status --short was empty before this report. This is a local unpublished tooling head. No remote check names, run IDs, completion states or conclusions were observed or queried by this reviewer. Required assurance is NOT OBSERVED; failure attribution is UNKNOWN. Local tests below are independent executions, not remote CI qualification. No joint/backend acceptance is claimed.

## Findings and nits

### JWR-01 — minor — detect truncated Content-Length responses before relaying them

- Location: docs/stg02/serve_recordings.py:190 (also line 206).
- Guarantee/invariant: joint forwarding must preserve the backend representation and distinguish an upstream transport failure from a complete backend response. It must not repair failed framing into an apparently complete representation.
- Concrete scenario: an owned upstream sends HTTP 200, Content-Length: 100 and two bytes `{}`, then closes. `HTTPResponse.read(amt)` returns those two bytes without raising IncompleteRead. The wrapper relays HTTP 200 and the source wire header with Content-Length: 2. This hides the early EOF. A transport failure in a command answer must remain a transport failure, rather than be reframed as the owner's complete reply.
- Reproduced independently with the probe below: `TRUNCATED: 200 ... ('Content-Length', '2') ... b'{}'`. The original eight tests do not exercise early EOF.
- Fix: retain bounded reads but verify response completion against the parsed framing before publishing source status/headers; reject premature EOF with the existing plain-text 502. Account for HEAD and bodyless statuses so valid no-body replies are preserved. Add independent regression coverage for truncated fixed-length and malformed chunked replies as appropriate.
- Affected scope/class: joint responses read with a bounded amount, principally fixed-length responses that close early. Mechanically enumerate every `response.read` call in this host (`rg -n 'response.read|Content-Length' docs/stg02/serve_recordings.py`); the probe supplies the missing framing case. Coverage limit: no exhaustive HTTP parser fuzzing or malicious upstream study is claimed; the concrete early-EOF defect is established.
- Confidence: high.

### JWR-02 — major — require exclusive Windows binding for the joint listener

- Location: docs/stg02/serve_recordings.py:227 (ThreadingHTTPServer construction).
- Guarantee/invariant: a successful startup/readiness observation must identify the reviewed wrapper serving the joint origin, and an already occupied listening address must fail startup. Exact-head traffic attribution is essential to the proposed joint evidence.
- Concrete scenario: a stale wrapper is already listening on the requested loopback port. On this Windows runtime, a second `create_server` successfully binds/listens on exactly the same address and port because the inherited HTTPServer enables SO_REUSEADDR. The new process can print its reviewed-head readiness message while requests reach the stale listener. The same issue applies to joint port 4252, though the reproduction uses only an owned ephemeral port.
- Reproduced independently with the probe below: `DUPLICATE BIND SUCCEEDED: 60052`. Both server constructors completed successfully; no real service port was touched.
- Fix: configure exclusive address use on Windows before binding (and avoid SO_REUSEADDR there), with a platform-appropriate server subclass/configuration. Preserve any intentional POSIX restart behavior. Add a regression proving a second listener for an owned occupied port fails, and ensure the CLI never prints readiness after a bind failure.
- Affected scope/class: Windows listeners created by this host; the unsafe constructor was inherited from fixture mode, but joint mode newly depends on it for exact-head origin attribution. Mechanically enumerate server constructors/socket options in this script with `rg -n 'ThreadingHTTPServer|reuse_address|EXCLUSIVEADDRUSE' docs/stg02/serve_recordings.py`. Coverage limit: exercised two copies of this host on this Windows/Python3.13.1 runtime, not all OS/listener combinations or browser routing under duplicate binding.
- Confidence: high.

No further findings or nits are held back by this pass.

## Independent verification and what looks sound

- Ran sibling mainrepo `.venv/Scripts/python.exe -I -B docs/stg02/test_joint_wrapper.py` with TEMP/TMP set to the writable GitHub workspace. Initial sandbox execution failed on socket connects with WinError10013, not code assertions. Repeated with approved loopback access: all 8 tests PASS (2.493 seconds). No dependency installation or Engine import was performed.
- Joint dispatch bypasses waiting/run validation and fixture generation; the test poisons waiting(). The host uses a fixed 127.0.0.1 upstream and forwards raw path/query and bytes. It does not parse JSON, follow redirects, retry requests, synthesize missing version headers, or forward/inject Authorization/Cookie.
- The selected request headers, response status/end-to-end headers, credentials exclusion, no startup/static probe, unavailable-upstream 502, non-API rejection, HEAD handling and default fixture waiting behavior are exercised by the independent standalone run. Response hop-by-hop filtering also removes fields named by Connection.
- CLI joint mode requires explicit upstream and static root; lifetime is finite; self-forwarding by explicit same port is rejected. Static serving retains root containment and CSP. Fixture local answering logic remains in the default branch. Full fixture/browser regression was not rerun; the standalone fixture test covers waiting only.
- Documentation correctly separates frozen UI assets from new wrapper source, warns that the joint steps/probes remain unrun, uses no bearer, and keeps test-route probes directed at the backend owner. The preserved prior report is not relabelled as current execution. App assets and contracts are unchanged in the complete delta.
- git diff --check passed for the exact base..head delta. No Docker build, UI freeze, browser suite or author clean-source checks were duplicated or adopted as independent evidence.

## Reproduction of both findings

From the repository root, pipe this Python to sibling mainrepo `.venv/Scripts/python.exe -I -B -` (on Windows, PowerShell `@' ... '@ | & 'C:/Users/Jon Smith/Documents/GitHub/Agentic-Engineering-Workflow/.venv/Scripts/python.exe' -I -B -`). It uses only owned ephemeral loopback ports and imports only the reviewed website host. Sandbox loopback access may require escalation.

```python
import http.client, importlib.util, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
spec = importlib.util.spec_from_file_location('w', 'docs/stg02/serve_recordings.py')
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)
class U(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Length', '100')
        self.send_header('X-AEW-Wire-Version', 'backend')
        self.end_headers()
        self.wfile.write(b'{}')
        self.wfile.flush()
        self.close_connection = True
u = ThreadingHTTPServer(('127.0.0.1', 0), U)
s = w.create_server(0, u.server_port, mode='joint')
for a in (u, s):
    threading.Thread(target=a.serve_forever, daemon=True).start()
c = http.client.HTTPConnection('127.0.0.1', s.server_port, timeout=3)
c.request('GET', '/v1/read/waiting')
r = c.getresponse()
print('TRUNCATED:', r.status, r.getheaders(), r.read())
c.close()
try:
    duplicate = w.create_server(s.server_port, u.server_port, mode='joint')
    print('DUPLICATE BIND SUCCEEDED:', s.server_port)
    duplicate.server_close()
except OSError as e:
    print('DUPLICATE BIND REJECTED:', repr(e))
for a in (s, u):
    a.shutdown()
    a.server_close()
```

Review: FINDINGS at 041595cff23c0d90d81c5ac2abc89b2a7bb05149
