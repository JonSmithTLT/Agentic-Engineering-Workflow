"""Run a synthetic worker relay and drive its Unix listener inside the integration test's trace."""

from __future__ import annotations

import http.client
import json
import socket
import sys
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

from aew.harness import runlog
from aew.harness.containment import netns, relay


def main(directory: Path, upstream: str, unused_proxy: str) -> None:
    # Relative socket names also work in long pytest temporary paths. The parent sets cwd to tmp_path.
    Path("net").mkdir()
    policy = {"containment": {"network": {"upstreams": {"openai": upstream}}}}
    env = {"OPENAI_API_KEY": "synthetic-destination-test", "HTTP_PROXY": unused_proxy}
    network = netns.RunNetwork.start(SimpleNamespace(network=netns.PROXY_ONLY, net_dir="net"), provider="openai",
                                     provider_env=["OPENAI_API_KEY"], policy=policy, env=env, relay_needed=True,
                                     record=relay.RequestLog(directory / runlog.RELAY_REQUESTS))
    statuses = []
    with closing(network):
        authorization = f"Bearer {network.sentinels['OPENAI_API_KEY']}"
        for method, path in (("POST", "/v1/responses"), ("GET", "/v1/models")):
            with socket.socket(socket.AF_UNIX) as sock, closing(http.client.HTTPConnection("localhost")) as connection:
                sock.settimeout(5)
                sock.connect(str(Path("net") / netns.RELAY))
                connection.sock = sock
                connection.request(method, path, headers={"Authorization": authorization})
                with connection.getresponse() as response:
                    response.read()
                    statuses.append(response.status)
    print(json.dumps(statuses))


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2], sys.argv[3])
