from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from tools import project_search as guard


class ProjectSearchTests(unittest.TestCase):
    def test_rejects_broad_and_protected_roots_before_filesystem_access(self):
        project = Path("/safe/project")
        for requested in ("/", "/home", "/home/test-user", "../sibling",
                          "/safe/project-other", "Windows.old", " DO NOT ENTER. ",
                          "a/Do Not Enter/b", "a/../b"):
            with self.subTest(root=requested), mock.patch.object(guard.os, "open") as opened:
                with self.assertRaises(guard.SearchRefused):
                    with guard.open_scope(project, requested):
                        self.fail("unsafe root accepted")
                opened.assert_not_called()

    def test_mount_fence_uses_metadata_without_visiting_target(self):
        mounts = guard.mount_paths(
            "1 0 8:1 / / rw - ext4 /dev/test rw\n"
            "2 1 8:2 / /safe/project/mounted\\040disk rw - fuseblk /dev/test2 rw\n"
        )
        for scope in (Path("/safe/project"), Path("/safe/project/mounted disk/child")):
            with self.assertRaises(guard.SearchRefused):
                guard.reject_nested_mounts(Path("/safe/project"), scope, mounts)
        guard.reject_nested_mounts(Path("/safe/project"), Path("/safe/project/tools"), mounts)

    def test_symlink_scope_is_never_followed(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            project.mkdir()
            (project / "escape").symlink_to("/not-an-authorized-path")
            with self.assertRaises(OSError):
                with guard.open_scope(project, "escape"):
                    self.fail("symlink root accepted")

    def test_command_is_fixed_and_has_no_host_home_mount(self):
        args = guard.parser().parse_args(["text", "tools", "--", "--follow"])
        options = guard.search_options(args)
        self.assertIn("--no-follow", options)
        self.assertIn("--one-file-system", options)
        self.assertIn("--no-config", options)
        self.assertEqual(options[-3:], ["-e", "--follow", "."])
        command = guard.sandbox_command(42, options)
        self.assertIn("--unshare-all", command)
        self.assertIn("--ro-bind-fd", command)
        self.assertNotIn("/home", command)
        self.assertNotIn("/mnt", command)
        self.assertNotIn("/media", command)

    def test_isolation_failure_does_not_retry_without_sandbox(self):
        with tempfile.TemporaryDirectory() as temporary:
            args = guard.parser().parse_args(["files", "."])
            with mock.patch.object(guard.subprocess, "run", return_value=subprocess.CompletedProcess([], 1)) as launched:
                self.assertEqual(guard.run(args, Path(temporary)), 1)
                self.assertEqual(launched.call_count, 1)
                self.assertEqual(launched.call_args.args[0][0], guard.BWRAP)

    @unittest.skipUnless(Path(guard.BWRAP).is_file() and Path(guard.RG_HOST).is_file(),
                         "requires installed bwrap and rg for the real sandbox check")
    def test_real_sandbox_searches_fixture_but_not_external_or_protected_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            project = base / "project"
            project.mkdir()
            outside = base / "outside"
            outside.mkdir()
            (outside / "secret.txt").write_text("outside_canary\n")
            (project / "good.txt").write_text("inside_canary\n")
            (project / "escape").symlink_to(outside, target_is_directory=True)
            (project / "escape-file.txt").symlink_to(outside / "secret.txt")
            for protected in ("Windows.old", " DO NOT ENTER. ", "nested/Windows.OLD"):
                directory = project / protected
                directory.mkdir(parents=True)
                (directory / "forbidden.txt").write_text("protected_canary\n")
            args = guard.parser().parse_args(["text", ".", "canary", "--glob", "**/*"])
            with tempfile.TemporaryFile(mode="w+") as stdout, tempfile.TemporaryFile(mode="w+") as stderr:
                result = guard.run(args, project, stdout=stdout, stderr=stderr)
                stdout.seek(0)
                stderr.seek(0)
                observed = stdout.read()
                self.assertEqual(result, 0, stderr.read())
            self.assertIn("inside_canary", observed)
            self.assertNotIn("outside_canary", observed)
            self.assertNotIn("protected_canary", observed)

            # Exercise the actual namespace separately from rg's no-follow:
            # the host fixture is absent, even when addressed directly.
            with guard.open_scope(project, ".") as fd:
                command = guard.sandbox_command(fd, [])
                marker = command.index("--", command.index("--cap-drop"))
                probe = command[:marker + 1] + ["/usr/bin/test", "!", "-e", str(outside)]
                checked = subprocess.run(probe, pass_fds=(fd,), capture_output=True,
                                         text=True, timeout=10)
                self.assertEqual(checked.returncode, 0, checked.stderr)


if __name__ == "__main__":
    unittest.main()
