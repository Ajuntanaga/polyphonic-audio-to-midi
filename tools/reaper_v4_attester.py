"""Non-admissible V4 attester skeleton; measured collectors are manifest-gated."""
from __future__ import annotations

import ctypes
import dataclasses
import pathlib
from collections.abc import Mapping

from tools import reaper_v4_protocol as protocol

__all__=("AttestationError","AttesterConfig","establish_protocol_barrier","validate_config")

PR_SET_DUMPABLE=4
CAPABILITY_STATUS_FIELDS=("CapInh","CapPrm","CapEff","CapAmb")
class AttestationError(RuntimeError): pass
@dataclasses.dataclass(frozen=True)
class AttesterConfig: data: Mapping[str,object]

def _status_text()->str:
    try: return pathlib.Path("/proc/self/status").read_text(encoding="utf-8")
    except OSError as exc: raise AttestationError("namespace capability status is unavailable") from exc
def establish_protocol_barrier(_config:Mapping[str,object])->None:
    libc=ctypes.CDLL(None,use_errno=True)
    if libc.prctl(PR_SET_DUMPABLE,0,0,0,0)!=0: raise AttestationError("PR_SET_DUMPABLE=0 was refused")
    values={line.partition(":")[0]:line.partition(":")[2].strip() for line in _status_text().splitlines()}
    for key in CAPABILITY_STATUS_FIELDS:
        if values.get(key)!="0000000000000000": raise AttestationError(f"namespace capability set is not empty: {key}")
def validate_config(config:AttesterConfig)->dict[str,object]:
    try: return protocol.validate_config(config.data)
    except protocol.ProtocolError as exc: raise AttestationError(str(exc)) from exc
