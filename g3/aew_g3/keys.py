"""Key custody (G3-09): a P-256 ECDSA key file in the service's state directory, mode 0600, on every host.

``key_id`` is the SHA-256 of the public key's DER ``SubjectPublicKeyInfo``. Rotating (``aew-g3 rotate-key``, root,
then a restart) keeps the retired public key beside the current key: a record signed under it stays verifiable for
audit from the published copy, and is never consumable (G3-08 step 1). The standard library has no P-256 ECDSA, so
this module uses ``cryptography`` with its defaults (review guide §10: standard libraries, no custom hardening).
"""

from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from .wire import canonical

KEY_FILE = "signing-key.pem"
RETIRED_DIR = "retired"


def _write_private(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)


def _public_der(key: ec.EllipticCurvePublicKey) -> bytes:
    return key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)


def key_id_of(key: ec.EllipticCurvePublicKey) -> str:
    return hashlib.sha256(_public_der(key)).hexdigest()


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


class KeyStore:
    """The current signing key and the retired public keys."""

    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir
        path = state_dir / KEY_FILE
        if not path.exists():
            _write_private(path, ec.generate_private_key(ec.SECP256R1()).private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        key = serialization.load_pem_private_key(path.read_bytes(), password=None)
        if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(key.curve, ec.SECP256R1):
            raise ValueError(f"{path} is not a P-256 key")
        self._key = key
        self.key_id = key_id_of(key.public_key())

    def sign(self, body: dict[str, Any]) -> str:
        """base64url of the ECDSA-SHA256 signature over the canonical JSON of ``body`` (G3-06)."""
        return _b64url(self._key.sign(canonical(body), ec.ECDSA(hashes.SHA256())))

    def verifies(self, record: dict[str, Any]) -> bool:
        """True only for a record signed by the CURRENT key: a retired key's records are not consumable (G3-09)."""
        sig = record.get("signature")
        if record.get("key_id") != self.key_id or not isinstance(sig, str):
            return False
        body = {k: v for k, v in record.items() if k != "signature"}
        try:
            self._key.public_key().verify(base64.urlsafe_b64decode(sig + "=" * (-len(sig) % 4)), canonical(body),
                                          ec.ECDSA(hashes.SHA256()))
        except (InvalidSignature, ValueError):
            return False
        return True

    def public_pems(self) -> dict[str, bytes]:
        """``key_id`` -> PEM public key, for the current key and every retired one (published for audit)."""
        out = {}
        retired = self.state_dir / RETIRED_DIR
        if retired.is_dir():
            for p in sorted(retired.glob("*.pub")):
                out[p.stem] = p.read_bytes()
        out[self.key_id] = self._key.public_key().public_bytes(serialization.Encoding.PEM,
                                                               serialization.PublicFormat.SubjectPublicKeyInfo)
        return out

    def publish(self, keys_dir: Path, issuer_ref: str) -> None:
        """Writes ``<key_id>.pub`` for every key (G3-09), and the service's ``issuer_ref`` (hand-off addendum 2 §2),
        into the runtime directory's ``keys/``, readable by all, so records can be audited and matched to a host."""
        keys_dir.mkdir(parents=True, exist_ok=True)
        files = {f"{kid}.pub": pem for kid, pem in self.public_pems().items()}
        files["issuer_ref"] = issuer_ref.encode("ascii") + b"\n"
        for name, data in files.items():
            tmp = keys_dir / f".{name}.new"
            tmp.write_bytes(data)
            os.chmod(tmp, 0o644)
            os.replace(tmp, keys_dir / name)


def rotate(state_dir: Path) -> tuple[str, str]:
    """Retires the current key (its public half stays for audit) and makes a new one. Returns (retired, new) ids."""
    old = KeyStore(state_dir)
    retired = state_dir / RETIRED_DIR
    retired.mkdir(mode=0o700, exist_ok=True)
    (retired / f"{old.key_id}.pub").write_bytes(old.public_pems()[old.key_id])
    (state_dir / KEY_FILE).unlink()  # a retired key never signs again, so its private half is not kept
    return old.key_id, KeyStore(state_dir).key_id
