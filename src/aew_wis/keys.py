"""WIS-09's key: a P-256 ECDSA key in a file in the issuer's ``StateDirectory``, mode 0600, owned by the service's
dynamic UID.

**P-256, in a file** (the operator's decisions of 2026-10-24 on WIS-A's findings, amending WIS-09 and G3-09): the file
key is P-256 ECDSA on every host, which RHEL 8's FIPS mode allows (it refuses Ed25519, the adopted text's file key,
F-2); and the TPM custody is parked, with the TPM device's group (F-1), so this build holds the key in the file on
every host. One algorithm is signed and verified, and :func:`verify` accepts nothing else.

``key_id`` is the SHA-256 of the public key's DER ``SubjectPublicKeyInfo`` (:func:`aew_wis.wire.key_id_of`). Every
public key the issuer has used is kept in its state (``keys/<key_id>.pub``, PEM) and published read-only in its
runtime directory at each start, so attestations under a retired key stay verifiable; only the current key's are ever
current (WIS-06, WIS-09). Rotation adds a ``key_id`` and destroys the retired private key file.

No private key material is ever logged, printed or written anywhere but the key file. A signature is ``r || s``,
32 bytes each, as hex (fixed length, whatever DER encoding the signer gives).
"""

from __future__ import annotations

import os
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature, encode_dss_signature

from aew_wis.wire import key_id_of

FILE_KEY = "p256.key"
PUBLIC_DIR = "keys"
_DER = serialization.Encoding.DER
_SPKI = serialization.PublicFormat.SubjectPublicKeyInfo
_ECDSA = ec.ECDSA(hashes.SHA256())
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_O_BINARY = getattr(os, "O_BINARY", 0)  # Windows: no newline translation of key bytes


class KeyUnavailable(Exception):
    """The issuer's key cannot be used: it refuses to start (or to attest) rather than sign with anything else."""


class Signer(Protocol):
    key_id: str
    public_der: bytes

    def sign(self, data: bytes) -> str: ...


def public_pem(public_der: bytes) -> bytes:
    return serialization.load_der_public_key(public_der).public_bytes(serialization.Encoding.PEM, _SPKI)


def p256_public(der: bytes) -> bytes:
    """``der`` as the canonical DER ``SubjectPublicKeyInfo`` of a P-256 key, or ``KeyUnavailable``."""
    key = serialization.load_der_public_key(der)
    if not (isinstance(key, ec.EllipticCurvePublicKey) and isinstance(key.curve, ec.SECP256R1)):
        raise KeyUnavailable("the key is not a P-256 key")
    return key.public_bytes(_DER, _SPKI)


def verify(public_der: bytes, data: bytes, signature_hex: str) -> bool:
    """Whether ``signature_hex`` is the P-256 key's ECDSA (SHA-256) signature over ``data``, as ``r || s``. Any other
    key, and anything malformed, is simply not a valid signature."""
    try:
        key = serialization.load_der_public_key(public_der)
        sig = bytes.fromhex(signature_hex)
        if not (isinstance(key, ec.EllipticCurvePublicKey) and isinstance(key.curve, ec.SECP256R1) and len(sig) == 64):
            return False
        key.verify(encode_dss_signature(int.from_bytes(sig[:32], "big"), int.from_bytes(sig[32:], "big")), data, _ECDSA)
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


def fsync_dir(path: Path) -> None:
    if sys.platform == "win32":
        return
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_new(path: Path, data: bytes, mode: int) -> None:
    """Create ``path`` with exactly ``mode`` (never through a link, never over an existing file), fsynced."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _O_NOFOLLOW | _O_BINARY, mode)
    try:
        if sys.platform != "win32":
            os.fchmod(fd, mode)  # not filtered by the umask
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    fsync_dir(path.parent)


def read_private(path: Path) -> bytes:
    """A private file's bytes, refused unless it is a regular file owned by this process's UID with mode 0600."""
    fd = os.open(path, os.O_RDONLY | _O_NOFOLLOW | _O_BINARY)
    try:
        st = os.fstat(fd)
        if sys.platform != "win32" and (not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid()
                                        or stat.S_IMODE(st.st_mode) != 0o600):
            raise KeyUnavailable(f"{path} must be a regular file of this service's UID with mode 0600; found mode "
                                 f"{stat.S_IMODE(st.st_mode):04o}, owner {st.st_uid}")
        return os.read(fd, 1 << 16)
    finally:
        os.close(fd)


@dataclass
class FileKey:
    """The key: PKCS#8 DER in ``p256.key``, read at start and held in memory only."""

    path: Path
    key_id: str
    public_der: bytes
    _key: ec.EllipticCurvePrivateKey

    @classmethod
    def load_or_create(cls, state_dir: Path) -> FileKey:
        path = state_dir / FILE_KEY
        if not path.exists():
            der = ec.generate_private_key(ec.SECP256R1()).private_bytes(
                _DER, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
            write_new(path, der, 0o600)
        try:
            key = serialization.load_der_private_key(read_private(path), password=None)
        except (ValueError, TypeError):
            raise KeyUnavailable(f"{path} does not hold a private key") from None
        if not (isinstance(key, ec.EllipticCurvePrivateKey) and isinstance(key.curve, ec.SECP256R1)):
            raise KeyUnavailable(f"{path} does not hold a P-256 key: root rotates it")
        der = key.public_key().public_bytes(_DER, _SPKI)
        return cls(path, key_id_of(der), der, key)

    def sign(self, data: bytes) -> str:
        r, s = decode_dss_signature(self._key.sign(data, _ECDSA))
        return (r.to_bytes(32, "big") + s.to_bytes(32, "big")).hex()

    def destroy(self) -> None:
        self.path.unlink()
        fsync_dir(self.path.parent)


def load_signer(state_dir: Path) -> FileKey:
    """The issuer's key, its public key recorded in the state."""
    try:
        signer = FileKey.load_or_create(state_dir)
    except KeyUnavailable:
        raise
    except (OSError, ValueError) as exc:
        raise KeyUnavailable(f"the issuer's key cannot be used: {exc}") from None
    record_public(state_dir, signer.public_der)
    return signer


def record_public(state_dir: Path, public_der: bytes) -> None:
    pub = state_dir / PUBLIC_DIR
    pub.mkdir(mode=0o700, exist_ok=True)
    path = pub / f"{key_id_of(public_der)}.pub"
    if not path.exists():
        write_new(path, public_pem(public_der), 0o644)


def rotate(state_dir: Path, signer: FileKey) -> FileKey:
    """WIS-09's rotation: the retired private key is destroyed, its public key kept, and a new key made."""
    signer.destroy()
    return load_signer(state_dir)


def recorded_publics(state_dir: Path) -> dict[str, bytes]:
    """Every public key the issuer has used, ``key_id`` -> PEM, each checked against its name and as P-256."""
    out = {}
    pub = state_dir / PUBLIC_DIR
    for path in sorted(pub.glob("*.pub")) if pub.is_dir() else []:
        pem = path.read_bytes()
        der = p256_public(serialization.load_pem_public_key(pem).public_bytes(_DER, _SPKI))
        if key_id_of(der) != path.stem:
            raise KeyUnavailable(f"{path} does not hold the public key its name says")
        out[path.stem] = pem
    return out
