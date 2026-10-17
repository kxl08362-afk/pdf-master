# Security policy

PDF Мастер 0.3.0 is an early desktop release. It has local regression and installation checks; no independent security audit or established vulnerability response SLA is claimed. Only the latest maintained release is a candidate for fixes. Older downloadable artifacts should not be interpreted as supported security branches.

## Reporting a concern

Do not publish exploit details, confidential PDFs, signature images, passwords, access tokens or unredacted logs in a public issue.

If the repository's **Security → Advisories → Report a vulnerability** option is available, use GitHub's private vulnerability reporting for [kxl08362-afk/pdf-master](https://github.com/kxl08362-afk/pdf-master/security/advisories/new). Its availability must be checked; publishing this file does not enable the feature. The recipient is the repository owner [kxl08362-afk](https://github.com/kxl08362-afk).

A dedicated private security email has not yet been supplied. If private reporting is unavailable, open a public issue containing only a request for a private contact channel, without the sensitive reproduction or exploit details. Wait for an agreed private channel before sending those materials. The maintainer should configure private reporting and confirm the contact channel before application submission.

Include the affected version and artifact SHA-256, Windows version, a concise impact description, reproduction steps and, when possible, a synthetic input. The project aims to assess reports and prepare a fix, but does not promise a particular response time. Coordinate disclosure with the maintainer.

## Scope and precautions

Relevant concerns include document parsing, unexpected file access, redaction failures, exposure of stored stamp images, installer behavior, release substitution and compromised build/signing workflows. The application uses native document/image libraries and is not a sandbox for hostile PDFs. Keep dependencies and Windows security updated; use extra isolation when investigating untrusted samples.

Preserve the original document. Check OCR text, especially numbers and legal or financial details. Before sharing a redacted PDF, verify the saved result and consider metadata, attachments and copies outside the selected region. A stamp image is not cryptographic proof of signing authority.

## Release integrity

Current 0.3.0 binaries are **unsigned**. Signing preparation is not a certificate or release approval. Obtain files only from the project's intended [release page](https://github.com/kxl08362-afk/pdf-master/releases), verify the version and published SHA-256, and retain the matching source. A checksum detects a mismatch against the published value; it does not independently establish publisher trust.

If signing is later enabled, inspect the downloaded executable's Authenticode status and certificate identity. A valid signature does not prove the absence of vulnerabilities. Report suspected signing compromise privately, stop requesting production signatures and update affected release notices while the issue is investigated. Responsibilities and approval status are recorded in [CODE_SIGNING.md](CODE_SIGNING.md).
