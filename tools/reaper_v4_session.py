from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from tools import reaper_v4_attester as attester
from tools import reaper_v4_child_runner as child_runner
from tools import reaper_v4_measurements as measurements
from tools import reaper_v4_protocol as protocol
from tools import reaper_v4_receipt_schema as receipt_schema


__all__ = (
    "SessionError",
    "SessionConfig",
    "SessionResult",
    "load_session_config",
    "run_session",
)

SESSION_ENTRYPOINT_KIND = "session_entrypoint"
SESSION_ENTRYPOINT_ROLE = "same_namespace_pre_ack_child_post_owner"
SESSION_CONFIG_PATH = "/run/m3-v4/session-config.json"
SESSION_DIGEST_PATH = "/run/m3-v4/session-config.sha256"


class SessionError(RuntimeError):
    pass


@dataclasses.dataclass(frozen=True, init=False)
class SessionConfig:
    data: Mapping[str, object]

    def __init__(self) -> None:
        raise SessionError("session execution is not admitted")


@dataclasses.dataclass(frozen=True, init=False)
class SessionResult:
    child_pid: int
    child_returncode: int
    pre_monotonic_ns: int
    post_monotonic_ns: int

    def __init__(self) -> None:
        raise SessionError("session execution is not admitted")


def load_session_config(config_path: str, digest_path: str) -> SessionConfig:
    raise SessionError("session execution is not admitted")


def run_session(config: SessionConfig) -> SessionResult:
    raise SessionError("session execution is not admitted")
