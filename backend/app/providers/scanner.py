"""Malware scanning hook. Every upload passes through a scanner before it is stored.

Today the only implementation is NoopScanner (status NOT_SCANNED). To enable real scanning, implement
`MalwareScanner` (for example a ClamAV client), add it to build_scanner(), and set MALWARE_SCANNER.
Downloads of files marked INFECTED are always refused.
"""

from typing import BinaryIO, Literal, Protocol

ScanStatus = Literal["CLEAN", "INFECTED", "NOT_SCANNED"]


class MalwareScanner(Protocol):
    def scan(self, stream: BinaryIO) -> ScanStatus: ...


class NoopScanner:
    def scan(self, stream: BinaryIO) -> ScanStatus:
        return "NOT_SCANNED"


def build_scanner(name: str) -> MalwareScanner:
    return NoopScanner()
