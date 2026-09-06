"""The one executable entrypoint for the bounded V4 session fixture."""
from __future__ import annotations

from tools import reaper_v4_session as session


def main() -> int:
    """Load only the fixed session configuration and run the single root."""
    config = session.load_session_config(
        session.SESSION_CONFIG_PATH,
        session.SESSION_DIGEST_PATH,
    )
    session.run_session(config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
