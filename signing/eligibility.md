# SignPath Foundation eligibility review

**Preparation only. Application not submitted; acceptance, MFA verification and production signing are pending.** This review does not certify eligibility. The intended repository is [kxl08362-afk/pdf-master](https://github.com/kxl08362-afk/pdf-master); verify its public state before relying on the links below.

The official [Foundation terms](https://signpath.org/terms) require an open-source, maintained and released project; review of its reputation; documented signing responsibilities; MFA for humans; verifiable builds and manual release approval. They also restrict commercial dual-licensing across components. Foundation acceptance is discretionary. These are prerequisites to resolve, not achievements implied by this file.

| Area | Evidence or honest current position | Before submission / production |
| --- | --- | --- |
| Application license | [LICENSE.txt](../LICENSE.txt): GNU AGPL-3.0-only. No separate proprietary license for this application's own code is proposed. | Publish all application code and build recipes at the stated repository. |
| Dependency licensing | The build uses the open-source PyMuPDF/MuPDF and PySide/Qt distributions; notices and sources are listed in [THIRD_PARTY.md](../THIRD_PARTY.md). | Obtain the Foundation's decision on the upstream licensing question below. Do not declare all-component eligibility already established. |
| Public project / release | Version 0.3.0 has been prepared locally, including an unsigned Windows installer. | Verify the public repository, a downloadable unsigned release, matching source, checksums and a passing GitHub build. Local artifacts are not public release evidence. |
| Reputation | New project, developed and tested on one Windows workstation; no established public user base, independent audit, press coverage or download statistics claimed. | Describe this plainly in the required Reputation field. Acceptance may be declined or postponed. |
| Maintainer and roles | One proposed human account: [kxl08362-afk](https://github.com/kxl08362-afk), serving author, reviewer and proposed signing approver. | Confirm ownership, exact account/contact identity and whether the Foundation accepts this single-maintainer arrangement. Do not invent a team or independent reviewer. |
| MFA and consent | Not verified here; no SignPath account permissions or consent given by this preparation. | Account holder confirms GitHub MFA, configures SignPath MFA, reads terms and gives required consent personally. |
| Verifiable signing build | GitHub Actions is the selected build system; signing is staged, not operational. | Follow the [official GitHub integration](https://docs.signpath.io/trusted-build-systems/github): GitHub-hosted jobs, retained unsigned workflow artifacts and provider origin verification. |
| Manual approval / metadata | [Proposed Code signing policy](../CODE_SIGNING.md). | Provision human approver and restrictive artifact policy only after acceptance. Check executable product name/version and every returned signature. |
| Privacy / uninstall | [Privacy policy](../PRIVACY.md); per-user Inno Setup installer has an uninstaller. Application-specific runtime source has no network upload or telemetry implementation. | Recheck each build and publish the policy on project/download pages. No all-service network audit is claimed. |
| Private contact | Required human first and last names are missing. The application contact email is handled in a private application copy and is not published here. Private GitHub reporting is not assumed enabled. | Supply the real human names and configure a verified private security reporting route. |

## Question to disclose to the Foundation

PyMuPDF/MuPDF is offered upstream under AGPL or a commercial license; Qt is offered under open-source and commercial alternatives. The application selects only their open-source terms. See [PyMuPDF's licensing explanation](https://pymupdf.readthedocs.io/en/latest/faq/index.html) and [Qt's open-source licensing explanation](https://www.qt.io/development/open-source-lgpl-obligations).

The Foundation's all-component dual-licensing condition may therefore be material even though this application's own code is AGPL-only. **Do not answer this question by assuming the chosen open-source option guarantees eligibility.** The copy-ready application text explicitly discloses both upstream alternatives and requests the Foundation's decision. If the Foundation rejects this dependency arrangement, production signing through this program cannot be represented as available without a real accepted remedy.

## Operational boundary

The signing target is project-owned output, not third-party libraries. Upstream binaries can remain in an installer with their own licenses; they must not be submitted for a project-owned signature. Existing local binaries are not a substitute for a trusted build artifact. Do not publish a Foundation acknowledgment as current until signing is accepted and actually used; retain the explicit unsigned status meanwhile.

The maintainer keeps the live form's field-by-field answers in a private application copy, excluded from the public repository because it contains contact information. No form submission, email, service registration or consent is performed by these documents.
