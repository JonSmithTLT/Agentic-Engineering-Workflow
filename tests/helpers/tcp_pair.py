"""A real TCP loopback pair on every platform (unlike AF_UNIX socketpair on Linux)."""

import socket


def tcp_pair(timeout: float = 5.0) -> tuple[socket.socket, socket.socket]:
    with socket.socket() as listener:
        listener.settimeout(timeout)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        client = socket.create_connection(listener.getsockname(), timeout=timeout)
        try:
            served, _ = listener.accept()
        except BaseException:
            client.close()
            raise
    served.settimeout(timeout)
    return client, served
