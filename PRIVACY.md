# Privacy policy

This policy describes the PDF Мастер 0.3.0 desktop application for Windows. Documents, recognized text, form values and signature or stamp images are processed locally. The application does not upload them to a server and does not contain an account system, advertising, telemetry, an analytics client or an automatic update checker.

This description is based on review of the application-specific source, including `app.py`, `ui.py`, `engine.py`, `pdf_tools.py`, `scan_preprocess.py` and `stamp_library.py`. It is not a claim that a network trace has proved the behavior of every operating-system service or third-party binary.

## Local data

| Data | Location and lifetime |
| --- | --- |
| Open PDF, recognition results and undo history | Working memory while the document is open; history is limited. The application does not promise secure erasure of process memory or the Windows page file. |
| Saved PDF, extracted text and exported images | The locations you select. The application does not automatically delete those files when you close it or uninstall it. |
| Signature / stamp library | Images and `index.json` under `%LOCALAPPDATA%\PDFMaster\stamps`, created when you explicitly save an item to the library. Names and images remain available across sessions. |
| Prepared stamp image | A temporary PNG may be written in the Windows temporary directory while inserting an image and is removed by the normal cleanup path. A crash can leave temporary files behind. |
| Saving and image export | Temporary or staging files may be created beside the selected destination. Successful saves use replacement; ordinary failure/cancellation paths attempt cleanup. This is not secure deletion. |
| Application error log | `%LOCALAPPDATA%\PDFMaster\logs\application.log`. Unhandled exceptions are logged locally and may contain file paths or other details supplied by an error. Logs are not sent automatically. |
| Explicit diagnostics / screenshots | Command-line self-tests create synthetic documents and a report at the location you request. The screenshot option writes a local image of the application window, which may contain a visible document. |
| Installer information | The installer stores application files, shortcuts, Windows uninstall information and a setup log. It installs for the current user. |

The stamp library and logs are separate from installed application files and may remain after uninstallation. Delete unneeded library entries within the application; after closing the application, you can also remove the corresponding local folders yourself. Keep a backup if you want to retain saved stamps. Deleting a library copy does not delete the original image you selected.

## Network boundaries

The shipped document tools use local libraries and bundled OCR language data. They do not call cloud OCR, AI services or third-party accounts. GitHub and any future SignPath integration are development and release services, not destinations for end-user documents. Visiting their websites in a browser is subject to their own policies, such as [GitHub's privacy statement](https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement) and [SignPath's privacy policy](https://signpath.io/privacy-policy).

Windows security, certificate validation, cloud-synced folders, antivirus software and software installed by the user can operate independently of this application. A file you choose to save in a synced folder may be transmitted by that separate service. This application does not control those services.

## Your documents and sensitive data

Only use signature or stamp images you are authorized to use. Inserting an image does not provide certificate-based electronic signing or verify the identity of a signer. Treat a stored signature image as sensitive and protect your Windows account and backups.

Visual cropping changes the displayed page area and is not a privacy eraser. The redaction tool removes selected page content when saved, but it does not promise to sanitize every attachment, metadata field, previous file, backup or unrelated page. Review the saved result before sharing it. OCR can make previously scanned information searchable.

## Questions and voluntary reports

The project contact is the repository owner [kxl08362-afk](https://github.com/kxl08362-afk). A dedicated privacy email has not been supplied. Use the project's [security reporting guidance](SECURITY.md) for sensitive concerns. Public issue reports are public: do not attach confidential PDFs, signature images, full logs or personal information. Share a synthetic or carefully sanitized reproduction whenever possible.
