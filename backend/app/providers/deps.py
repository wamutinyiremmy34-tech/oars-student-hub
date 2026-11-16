from typing import Annotated

from fastapi import Depends, Request

from app.providers.scanner import MalwareScanner
from app.providers.storage.base import StorageBackend


def get_storage(request: Request) -> StorageBackend:
    storage: StorageBackend = request.app.state.storage
    return storage


def get_scanner(request: Request) -> MalwareScanner:
    scanner: MalwareScanner = request.app.state.scanner
    return scanner


StorageDep = Annotated[StorageBackend, Depends(get_storage)]
ScannerDep = Annotated[MalwareScanner, Depends(get_scanner)]
