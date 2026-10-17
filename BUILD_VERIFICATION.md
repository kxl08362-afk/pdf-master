# Build verification

Application version: **0.3.0**, Windows 11 x64.

## Public GitHub build and release

[GitHub Actions run 39067439115](https://github.com/kxl08362-afk/pdf-master/actions/runs/39067439115) completed successfully for commit `57431a7b7c3989a62e73586cfe25578eb26938dc` on GitHub-hosted Windows Server 2025 with CPython 3.12.14. All **100 tests and 76 subtests passed, with no skipped tests**. Dependency checks, source/frozen-bytecode agreement for all ten modules, installer compilation and frozen application self-test passed.

The [public unsigned release v0.3.0](https://github.com/kxl08362-afk/pdf-master/releases/tag/v0.3.0) contains the installer downloaded from that run's artifact, not a workstation rebuild. `PDFMaster-Setup-0.3.0.exe` is 78,185,191 bytes; SHA256 is `0ee616b236efae66304c09f15b4cb7e75cc06c5b80e56386d3b76fd0c17ba975`. GitHub's published asset digest matches this value. This verifies the published build's origin and checks; no signing request or Foundation acceptance has occurred.

## Earlier local verification

The application passed 74 automated tests and 58 subtests in the last complete local application run. These cover real Russian/English OCR, text replacement, signature placement, AcroForms, page operations, lossless conversion/optimization and navigation. A standalone installed build passed all nine diagnostic groups with external Python/OCR removed from PATH. Silent installation and uninstallation returned zero; a user-created document survived removal unchanged.

This earlier local verification is separate from the public hosted build above. Every CI build produces its own test results, checksums and build manifest.

The existing 0.3.0 installer is unsigned. Its SHA256 is `55c962daf3efad8cff044e3bd0db9823cabcbc8cfb44c1967a1a0672964c4f8c`. Rebuilding with updated documentation, build tools or runner images produces a different binary; this value identifies the previously tested installer only.

No clean virtual machine or second physical computer was used for the local record. SmartScreen reputation, Foundation acceptance, maintainer MFA and a production certificate remain external verification steps. See [Code signing policy](CODE_SIGNING.md).
