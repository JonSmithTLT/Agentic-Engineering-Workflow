"""``python -m aew_wis``: the issuer's commands, run from root's install (``/opt/aew-wis/bin/aew-wis``), never from the
operator's editable checkout.

* ``serve <instance> [--read-interval S] [--renew-before S] [--validity S] [--view-age S] [--runtime-max S]``: the
  issuer, as ``aew-wis-issuer@<instance>.service`` runs it (:func:`aew_wis.service.serve`);
* ``manifest [--install-root DIR]``: WIS-12's install manifest on this host, as JSON on standard output, with exit
  status 1 when its two detectors disagree (:func:`aew_wis.manifest.host_manifest`). It reads files and asks systemd
  what it loaded; it changes nothing.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from aew_wis import manifest, service

USAGE = ("usage: aew-wis serve <instance> [--read-interval S] [--renew-before S] [--validity S] [--view-age S] "
         "[--runtime-max S]\n       aew-wis manifest [--install-root DIR]")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) >= 2 and argv[0] == "serve":
        return service.serve(argv[1], argv[2:])
    if argv[:1] == ["manifest"] and len(argv) in (1, 3) and (len(argv) == 1 or argv[1] == "--install-root"):
        try:
            result = manifest.host_manifest(Path(argv[2]) if len(argv) == 3 else manifest.INSTALL_ROOT)
        except (manifest.ManifestRefused, OSError) as exc:
            print(f"aew-wis manifest: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result, indent=1, sort_keys=True))
        return 1 if result["problems"] else 0
    print(USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
