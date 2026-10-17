"""Synthetic public-source export tests; no GitHub writes or real credentials."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import prepare_repository as repository


class RepositoryReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.destination = self.root / "public"
        self.source.mkdir()
        for name in (*repository.ROOT_FILES, *repository.INSTALLER_FILES, "openspec/config.yaml"):
            self.write_source(name, "# fixture\n")
        for folder in (*repository.FOLDERS, "installer/hooks"):
            (self.source / folder).mkdir(parents=True, exist_ok=True)
        self.write_source("resources/tessdata/rus.traineddata", b"fixture-model\x00\x01")
        self.write_source("licenses/component-LICENSE.txt", "Fixture component license\n")
        self.write_source("tests/test_example.py", "def test_example(): assert True\n")
        self.write_source("installer/hooks/hook-example.py", "# fixture hook\n")
        self.write_source("openspec/specs/example/spec.md", "# Product requirement\n")

    def write_source(self, relative, content):
        path = self.source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
        return path

    def prepare(self):
        return repository.prepare_repository(self.source, self.destination)

    def read_manifest(self):
        return json.loads((self.destination / "repository-manifest.json").read_text(encoding="utf-8"))

    def write_manifest(self, value):
        (self.destination / "repository-manifest.json").write_text(json.dumps(value), encoding="utf-8")

    def test_allowlist_exports_required_runtime_docs_models_and_manifest(self):
        files = repository.collect_files(self.source)
        self.assertEqual(files, sorted(set(files)))
        self.assertTrue(all(path.is_absolute() for path in files))
        result = self.prepare()
        self.assertTrue(result["ok"])
        self.assertEqual(repository.check_repository(self.destination), result)
        manifest = self.read_manifest()
        self.assertEqual(result["files"], len(manifest["files"]))
        for name in (*repository.ROOT_FILES, *repository.INSTALLER_FILES):
            self.assertIn(name, manifest["files"])
        self.assertIn("resources/tessdata/rus.traineddata", manifest["files"])
        self.assertIn("openspec/specs/example/spec.md", manifest["files"])
        self.assertEqual(manifest["files"]["app.py"]["sha256"], hashlib.sha256((self.source / "app.py").read_bytes()).hexdigest())
        self.assertNotIn(str(self.source), json.dumps(manifest))
        self.assertNotIn(str(self.destination), json.dumps(manifest))
        self.assertNotIn("github", result)

    def test_excludes_local_artifacts_history_private_application_and_nested_caches(self):
        excluded = [
            ".venv/package.py", "build/app.pkg", "dist/app.exe", "qa/installation.json",
            ".agents/session.md", ".git/config", ".codex/history.jsonl",
            "installer/tools/compiler.exe", "openspec/changes/archive/old-session/design.md",
            "VERIFICATION.md", "docs/signpath-application.md", "personal-client.pdf",
            "scripts/__pycache__/cached.pyc", "resources/qa/private.json", "tests/.pytest_cache/status",
        ]
        for name in excluded:
            self.write_source(name, "private fixture, never export\n")
        self.prepare()
        published = set(self.read_manifest()["files"])
        self.assertTrue(published.isdisjoint(excluded))
        self.assertFalse((self.destination / "qa").exists())
        self.assertFalse((self.destination / ".agents").exists())

    def test_rejects_missing_required_file_without_partial_destination(self):
        (self.source / "app.py").unlink()
        with self.assertRaisesRegex(ValueError, "missing"):
            self.prepare()
        self.assertFalse(self.destination.exists())

    def test_destination_must_be_new_and_outside_source_tree(self):
        for path in [self.source, self.source / "nested-export", self.root]:
            with self.subTest(path=path), self.assertRaises(ValueError):
                repository.prepare_repository(self.source, path)
        self.destination.mkdir()
        marker = self.destination / "keep.txt"
        marker.write_text("preserve me", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            self.prepare()
        self.assertEqual(marker.read_text(encoding="utf-8"), "preserve me")

    def test_rejects_private_key_and_environment_files_inside_allowed_tree(self):
        for suffix in ["certificate.pfx", "certificate.p12", "private.key", "private.pem", ".env", ".env.local"]:
            with self.subTest(suffix=suffix):
                path = self.write_source("signing/" + suffix, "fixture private material")
                with self.assertRaisesRegex(ValueError, "Private"):
                    repository.collect_files(self.source)
                path.unlink()

    def test_detects_dummy_credential_patterns_without_exposing_values(self):
        candidates = ["ghp_" + "A" * 36, "github_pat_" + "B" * 36,
                      "-----BEGIN " + "PRIVATE KEY-----\nfixture\n"]
        for value in candidates:
            with self.subTest(pattern_length=len(value)):
                self.write_source("README.md", value)
                with self.assertRaisesRegex(ValueError, "credential") as raised:
                    repository.collect_files(self.source)
                self.assertNotIn(value, str(raised.exception))

    def test_rejects_private_absolute_user_paths_in_public_docs(self):
        for value in ["C:" + "/Users/" + "Someone/Documents/private.pdf",
                      "/home/" + "someone/private.pdf"]:
            with self.subTest(path_kind=value.split("/")[0]):
                self.write_source("README.md", value)
                with self.assertRaisesRegex(ValueError, "Private absolute"):
                    repository.collect_files(self.source)

    def test_does_not_publish_oversized_git_blob(self):
        path = self.source / "resources/oversized.bin"
        with path.open("wb") as output:
            output.truncate(repository.MAX_FILE_BYTES + 1)
        with self.assertRaisesRegex(ValueError, "size limit"):
            repository.collect_files(self.source)

    def test_rejects_symlink_to_file_outside_public_tree(self):
        outside = self.root / "outside.txt"
        outside.write_text("private fixture", encoding="utf-8")
        link = self.source / "resources/linked.txt"
        try:
            link.symlink_to(outside)
        except OSError as exc:
            self.skipTest("Symlink creation unavailable: " + str(exc.winerror if hasattr(exc, "winerror") else exc.errno))
        with self.assertRaisesRegex(ValueError, "Symlinks"):
            repository.collect_files(self.source)

    @unittest.skipUnless(os.name == "nt", "NTFS junction check applies to Windows")
    def test_rejects_windows_junction_without_following_private_directory(self):
        powershell = shutil.which("pwsh") or shutil.which("powershell")
        if not powershell:
            self.skipTest("PowerShell unavailable")
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "notice.txt").write_text("private fixture", encoding="utf-8")
        junction = self.source / "resources/junction"
        quote = lambda path: "'" + str(path).replace("'", "''") + "'"
        command = "New-Item -ItemType Junction -Path " + quote(junction) + " -Target " + quote(outside) + " | Out-Null"
        result = subprocess.run([powershell, "-NoProfile", "-NonInteractive", "-Command", command],
                                capture_output=True, timeout=20, creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode:
            self.skipTest("NTFS junction creation unavailable")
        self.assertTrue(junction.is_junction())
        # Both junction and target are inside this test's TemporaryDirectory.
        self.assertTrue(junction.resolve().is_relative_to(self.root.resolve()))
        with self.assertRaisesRegex(ValueError, "Symlinks"):
            repository.collect_files(self.source)
        self.assertEqual((outside / "notice.txt").read_text(encoding="utf-8"), "private fixture")

    def test_checksum_detects_same_length_corruption_and_missing_file(self):
        self.prepare()
        path = self.destination / "app.py"
        original = path.read_bytes()
        path.write_bytes(b"!" + original[1:])
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            repository.check_repository(self.destination)
        path.unlink()
        with self.assertRaisesRegex(ValueError, "Missing"):
            repository.check_repository(self.destination)

    def test_rejects_unlisted_file_and_manifest_path_traversal(self):
        self.prepare()
        extra = self.destination / "extra.txt"
        extra.write_text("unlisted", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Unlisted"):
            repository.check_repository(self.destination)
        extra.unlink()
        manifest = self.read_manifest()
        manifest["files"]["../outside.txt"] = {"bytes": 0, "sha256": "0" * 64}
        self.write_manifest(manifest)
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            repository.check_repository(self.destination)

    def test_manifest_cannot_remove_mandatory_runtime_file(self):
        self.prepare()
        (self.destination / "app.py").unlink()
        manifest = self.read_manifest()
        del manifest["files"]["app.py"]
        self.write_manifest(manifest)
        with self.assertRaises(ValueError):
            repository.check_repository(self.destination)

    def test_manifest_cannot_allow_list_excluded_qa_history(self):
        self.prepare()
        path = self.destination / "qa/session.txt"
        path.parent.mkdir()
        path.write_text("private fixture", encoding="utf-8")
        manifest = self.read_manifest()
        manifest["files"]["qa/session.txt"] = {"bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        self.write_manifest(manifest)
        with self.assertRaises(ValueError):
            repository.check_repository(self.destination)

    def test_invalid_utf8_does_not_bypass_credential_scan(self):
        self.write_source("README.md", b"\xff" + ("ghp_" + "A" * 36).encode("ascii"))
        with self.assertRaises(ValueError):
            repository.collect_files(self.source)

    def test_export_normalizes_bom_crlf_and_hashes_exported_bytes(self):
        self.write_source("app.py", b"# fixture\r\n")
        self.write_source("README.md", b"\xef\xbb\xbf" + "Описание\r\n".encode("utf-8"))
        self.prepare()
        self.assertEqual((self.destination / "app.py").read_bytes(), b"# fixture\n")
        self.assertEqual((self.source / "app.py").read_bytes(), b"# fixture\r\n")
        self.assertEqual((self.destination / "README.md").read_bytes(), "Описание\n".encode("utf-8"))
        manifest = self.read_manifest()
        exported = (self.destination / "app.py").read_bytes()
        self.assertEqual(manifest["files"]["app.py"], {"bytes": len(exported), "sha256": hashlib.sha256(exported).hexdigest()})

    def test_optional_git_initialization_never_pushes_or_sets_remote(self):
        with patch.object(repository.subprocess, "run") as execute:
            result = repository.prepare_repository(self.source, self.destination, initialize_git=True)
        self.assertTrue(result["ok"])
        commands = [call.args[0] for call in execute.call_args_list]
        self.assertEqual(len(commands), 2)
        self.assertEqual(commands[0][:3], ["git", "init", "--initial-branch=main"])
        self.assertEqual(commands[1][-2:], ["add", "--all"])
        self.assertFalse(any(word in {"push", "remote", "clone", "fetch"} for command in commands for word in command))


if __name__ == "__main__":
    unittest.main()
