"""Regression coverage for the sole V4 executable session entrypoint."""
from __future__ import annotations

import importlib
import unittest
from unittest import mock


class SessionEntrypointTests(unittest.TestCase):
    def test_loads_only_the_fixed_pair_then_runs_the_single_session_root(self) -> None:
        entry = importlib.import_module("tools.reaper_v4_session_entry")
        configuration = object()
        with (
            mock.patch.object(entry.session, "load_session_config", return_value=configuration) as load,
            mock.patch.object(entry.session, "run_session") as run,
        ):
            self.assertEqual(entry.main(), 0)
        load.assert_called_once_with(
            entry.session.SESSION_CONFIG_PATH,
            entry.session.SESSION_DIGEST_PATH,
        )
        run.assert_called_once_with(configuration)


if __name__ == "__main__":
    unittest.main()
