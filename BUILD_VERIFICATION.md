# Build verification

Application version: **0.3.0**, Windows 11 x64.

The application passed 74 automated tests and 58 subtests in the last complete local application run. These cover real Russian/English OCR, text replacement, signature placement, AcroForms, page operations, lossless conversion/optimization and navigation. A standalone installed build passed all nine diagnostic groups with external Python/OCR removed from PATH. Silent installation and uninstallation returned zero; a user-created document survived removal unchanged.

This is a local verification record, not evidence of a cloud build or SignPath approval. Current cloud status and exact commit/run details are available in [GitHub Actions](https://github.com/kxl08362-afk/pdf-master/actions). Every CI build produces its own test results, checksums and build manifest. Additional repository/CI checks are added with the signing preparation.

The existing 0.3.0 installer is unsigned. Its SHA256 is `55c962daf3efad8cff044e3bd0db9823cabcbc8cfb44c1967a1a0672964c4f8c`. Rebuilding with updated documentation, build tools or runner images produces a different binary; this value identifies the previously tested installer only.

No clean virtual machine or second physical computer was used for the local record. SmartScreen reputation, Foundation acceptance, maintainer MFA and a production certificate remain external verification steps. See [Code signing policy](CODE_SIGNING.md).
