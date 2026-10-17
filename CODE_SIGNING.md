# Code signing policy

**Current status: PDF Мастер 0.3.0 is unsigned. SignPath Foundation approval and production signing have not been obtained.** Preparing a workflow or publishing this policy does not make existing downloads signed. Windows may show an unknown-publisher warning; do not disable Windows security to install the application.

Project links:

- [Source and project home](https://github.com/kxl08362-afk/pdf-master)
- [Downloads and release notes](https://github.com/kxl08362-afk/pdf-master/releases)
- [Privacy policy](PRIVACY.md)
- [Eligibility review and unresolved prerequisites](signing/eligibility.md)

The repository and release URLs above are the intended public locations. Their availability and a successful public build must be verified before the application is submitted.

## Responsibilities

The project currently identifies one proposed human maintainer, GitHub owner [kxl08362-afk](https://github.com/kxl08362-afk). No organization, additional reviewers or independent approval team is claimed.

| Role | Responsible account | Scope and status |
| --- | --- | --- |
| Author / committer | kxl08362-afk | Application source, dependencies and build instructions; confirm repository ownership before enrollment. |
| Reviewer | kxl08362-afk | Reviews outside contributions and changes to build/signing configuration. A separate reviewer has not been appointed. |
| Release signing approver | kxl08362-afk, proposed | Must inspect the exact release and manually approve each request if this role arrangement is accepted by SignPath. No production role is provisioned yet. |

These are proposed responsibilities, not a claim of two-person review. The account holder must confirm multi-factor authentication for GitHub and SignPath before receiving signing permissions. MFA status has not been independently verified. Future human members must meet the same requirement before access is granted.

## Release controls

Production signing remains disabled until SignPath accepts the project, resolves the dependency licensing question, and provisions the necessary project and policy. An approval is a human decision for a particular build; successful CI is not an approval.

The intended release path is a public source commit and version tag, a successful build and tests on GitHub-hosted Windows runners, retained unsigned workflow artifacts, origin verification, human signing approval, and verification of the returned Authenticode signatures before publication. The artifact configuration must constrain project-owned executable names, product metadata and version. Expected application targets are `PDFMaster.exe` and `PDFMaster-Setup-<version>.exe`; the final allowed paths depend on the reviewed artifact configuration.

Upstream DLLs may be included with their notices. This project does not claim authorship of those libraries and will not request its own project signature for them. Protect the submitting credential, reject untrusted pull-request signing requests, and do not authorize arbitrary local uploads as substitutes for verified builds. See the official [GitHub build integration](https://docs.signpath.io/trusted-build-systems/github).

A release is described as signed only after the downloaded release artifacts have been checked for a valid signature, expected certificate identity and version. Any unsigned release remains explicitly marked unsigned, with its checksums and matching source.

## Conditional acknowledgment

If production signing is approved and actually used, update this policy and the corresponding release/download pages with the confirmed status and the acknowledgment required by the [SignPath Foundation terms](https://signpath.org/terms). The following wording is reserved for that future state and is **not a statement about current releases**:

> Free code signing provided by SignPath.io, certificate by SignPath Foundation.

Use links to [SignPath.io](https://about.signpath.io/) and [SignPath Foundation](https://signpath.org/) in that acknowledgment. Keep the role list and [privacy policy](PRIVACY.md) linked from the project homepage and download pages. If signing is suspended or revoked, update affected release notices and stop requesting production signatures until resolved.
