"""Local CI/signing configuration checks; these do not assert a live CI run."""
from pathlib import Path
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

import yaml

ROOT = Path(__file__).resolve().parents[1]


def workflow(name):
    # YAML 1.1 safe_load treats an unquoted `on` as bool; preserve GitHub's key.
    return yaml.load((ROOT / ".github/workflows" / name).read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def all_steps(document):
    return [step for job in document["jobs"].values() for step in job.get("steps", [])]


class WorkflowPreparationTests(unittest.TestCase):
    def test_yaml_events_and_pinned_remote_actions(self):
        for name in ["windows-ci.yml", "sign-release.yml"]:
            with self.subTest(workflow=name):
                document = workflow(name)
                self.assertIn("on", document)
                self.assertNotIn("pull_request_target", document["on"])
                self.assertNotIn("workflow_run", document["on"])
                self.assertIsInstance(document["jobs"], dict)
                for step in all_steps(document):
                    if "uses" in step:
                        self.assertRegex(step["uses"], r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+@[a-f0-9]{40}$")
                for job in document["jobs"].values():
                    if "uses" in job:
                        self.assertEqual(job["uses"], "./.github/workflows/windows-ci.yml")

    def test_unsigned_pull_request_build_has_read_only_token_and_no_secrets(self):
        document = workflow("windows-ci.yml")
        self.assertIn("pull_request", document["on"])
        self.assertIn("workflow_call", document["on"])
        self.assertEqual(document["permissions"], {"contents": "read"})
        self.assertNotIn("secrets.", json.dumps(document))
        self.assertNotIn("secrets: inherit", (ROOT / ".github/workflows/windows-ci.yml").read_text(encoding="utf-8"))
        for job in document["jobs"].values():
            self.assertEqual(job["runs-on"], "windows-2025")
            self.assertNotIn("environment", job)
        checkout = next(step for step in all_steps(document) if step.get("uses", "").startswith("actions/checkout@"))
        self.assertEqual(checkout["with"]["persist-credentials"], "false")
        self.assertIn("ci_build.ps1 -Phase Build", "\n".join(step.get("run", "") for step in all_steps(document)))

    def test_signing_is_manual_main_only_protected_and_fail_closed(self):
        document = workflow("sign-release.yml")
        self.assertEqual(set(document["on"]), {"workflow_dispatch"})
        self.assertEqual(document["permissions"], {"contents": "read", "actions": "read"})
        jobs = document["jobs"]
        self.assertEqual(jobs["sign"]["environment"], "signpath-release")
        self.assertIn("github.event_name == 'workflow_dispatch'", jobs["sign"]["if"])
        self.assertIn("github.ref == 'refs/heads/main'", jobs["sign"]["if"])
        self.assertEqual(set(jobs["sign"]["needs"]), {"readiness", "build"})
        self.assertEqual(jobs["build"]["needs"], "readiness")
        self.assertEqual(jobs["build"]["permissions"], {"contents": "read"})
        self.assertNotIn("secrets", jobs["build"])
        readiness = "\n".join(step.get("run", "") for step in jobs["readiness"]["steps"])
        for gate in ["SIGNPATH_ENABLED", "refs/heads/main", "required_reviewers", "custom_branch_policies", "deployment-branch-policies"]:
            self.assertIn(gate, readiness)
        self.assertIn("throw", readiness)
        self.assertNotIn("secrets.", json.dumps(jobs["readiness"]))
        self.assertNotIn("contents: write", (ROOT / ".github/workflows/sign-release.yml").read_text(encoding="utf-8"))

    def test_signing_uses_exact_build_artifact_ids_and_checks_cert_timestamp(self):
        document = workflow("sign-release.yml")
        steps = document["jobs"]["sign"]["steps"]
        signers = [step for step in steps if step.get("uses", "").startswith("signpath/")]
        self.assertEqual(len(signers), 2)
        self.assertEqual(signers[0]["with"]["github-artifact-id"], "${{ needs.build.outputs.unsigned_application_artifact_id }}")
        self.assertEqual(signers[1]["with"]["github-artifact-id"], "${{ steps.outer.outputs.artifact-id }}")
        for step in signers:
            self.assertEqual(step["with"]["wait-for-completion"], "true")
            self.assertEqual(step["with"]["api-token"], "${{ secrets.SIGNPATH_API_TOKEN }}")
        unsigned = workflow("windows-ci.yml")
        own_upload = next(step for step in all_steps(unsigned) if step.get("id") == "application")
        self.assertEqual(own_upload["with"]["path"], "dist/PDFMaster/PDFMaster.exe")
        outer = next(step for step in steps if step.get("id") == "outer")
        self.assertTrue(outer["with"]["path"].startswith("dist/installers/PDFMaster-Setup-"))
        self.assertEqual(outer["with"]["if-no-files-found"], "error")
        runs = "\n".join(step.get("run", "") for step in steps)
        self.assertIn("Get-AuthenticodeSignature", runs)
        self.assertIn("SignerCertificate.Thumbprint", runs)
        self.assertIn("TimeStamperCertificate", runs)
        self.assertIn("-Phase VerifySigned", runs)
        self.assertNotIn("gh release create", runs)

    def test_signpath_artifact_xml_limits_signing_to_two_own_executables(self):
        expected = {
            "artifact-configuration.xml": "PDFMaster.exe",
            "installer-artifact-configuration.xml": "PDFMaster-Setup-${version}.exe",
        }
        namespace = {"s": "http://signpath.io/artifact-configuration/v1"}
        for name, filename in expected.items():
            with self.subTest(configuration=name):
                root = ET.parse(ROOT / "signing" / name).getroot()
                files = root.findall(".//s:pe-file", namespace)
                self.assertEqual(len(files), 1)
                self.assertEqual(files[0].attrib["path"], filename)
                self.assertEqual(files[0].attrib["min-matches"], "1")
                self.assertEqual(files[0].attrib["max-matches"], "1")
                self.assertIsNotNone(files[0].find("s:authenticode-sign", namespace))
                self.assertIsNotNone(root.find("s:zip-file", namespace))
                for element in root.iter():
                    for value in element.attrib.values():
                        self.assertNotIn(".dll", value.lower())
                        self.assertNotIn("*", value)
                        self.assertNotIn("..", value)
        script = (ROOT / "scripts/ci_build.ps1").read_text(encoding="utf-8")
        self.assertIn("Assert-UpstreamUnchanged", script)
        self.assertIn("$name -ne 'PDFMaster.exe'", script)

    def test_bootstrap_pins_hashes_and_validates_before_install_or_extract(self):
        source = (ROOT / "scripts/prepare_ci_tools.ps1").read_text(encoding="utf-8")
        for name in ["pythonHash", "innoHash"]:
            self.assertRegex(source, rf"\${name}\s*=\s*'[a-f0-9]{{64}}'")
        urls = re.findall(r"\$(?:pythonUrl|innoUrl)\s*=\s*'([^']+)'", source)
        self.assertEqual(len(urls), 2)
        self.assertTrue(all(url.startswith("https://github.com/") and "/releases/download/" in url for url in urls))
        self.assertTrue(all("latest" not in url for url in urls))
        download = source.split("function Get-PinnedDownload {", 1)[1].split("\n}\n", 1)[0]
        self.assertLess(download.index("Assert-FileSha256 $partial $Sha256"), download.index("Move-Item"))
        self.assertIn("Assert-FileSha256 $Destination $Sha256", download)
        self.assertLess(source.index("Get-PinnedDownload $pythonUrl"), source.index("& tar.exe"))
        self.assertLess(source.index("Get-PinnedDownload $innoUrl"), source.index("Start-Process -FilePath $innoInstaller"))
        self.assertLess(source.index("Get-AuthenticodeSignature -LiteralPath $innoInstaller"), source.index("Start-Process -FilePath $innoInstaller"))
        self.assertIn("not a CI download attestation", source)


class BootstrapHashFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.powershell = shutil.which("pwsh") or shutil.which("powershell")
        if not cls.powershell:
            raise unittest.SkipTest("PowerShell unavailable")

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.fixture = self.root / "download-fixture.bin"
        self.data = b"known synthetic download bytes\x00\x01"
        self.fixture.write_bytes(self.data)
        self.sha256 = hashlib.sha256(self.data).hexdigest()

    def verify(self, expected, path=None):
        options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
        return subprocess.run([self.powershell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
            "-File", str(ROOT / "scripts/prepare_ci_tools.ps1"), "-VerifyOnly", "-File", str(path or self.fixture),
            "-ExpectedSha256", expected], cwd=self.root, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=30, **options)

    def test_matching_hash_verifies_without_download_install_or_extra_files(self):
        result = self.verify(self.sha256.upper())
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout.lstrip("\ufeff"))
        self.assertTrue(report["verified"])
        self.assertEqual(report["sha256"], self.sha256)
        self.assertEqual(self.fixture.read_bytes(), self.data)
        self.assertEqual(set(self.root.iterdir()), {self.fixture})

    def test_same_length_download_corruption_fails_closed(self):
        self.fixture.write_bytes(b"X" + self.data[1:])
        result = self.verify(self.sha256)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SHA256 mismatch", result.stderr)
        self.assertNotIn('"verified": true', result.stdout.lower())
        self.assertEqual(set(self.root.iterdir()), {self.fixture})

    def test_missing_file_and_invalid_hash_are_rejected(self):
        missing = self.verify(self.sha256, self.root / "missing.bin")
        self.assertNotEqual(missing.returncode, 0)
        self.assertIn("Tool file missing", missing.stderr)
        invalid = self.verify("invalid-digest")
        self.assertNotEqual(invalid.returncode, 0)
        self.assertEqual(self.fixture.read_bytes(), self.data)


if __name__ == "__main__":
    unittest.main()
