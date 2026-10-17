"""Export a reviewable public source tree, without developer/private state.

The repository owner chooses when to publish; this module never contacts GitHub.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess


ROOT_FILES = (
    'app.py', 'engine.py', 'ui.py', 'diagnostics.py', 'pdf_tools.py',
    'stamp_library.py', 'scan_preprocess.py', 'command_menu.py', 'ui_theme.py', 'ui_icons.py',
    'PDFMaster.spec', 'build.ps1', 'requirements.txt', 'requirements-dev.txt',
    'README.md', 'LICENSE.txt', 'THIRD_PARTY.md', 'SOURCES.md',
    'CODE_SIGNING.md', 'PRIVACY.md', 'CONTRIBUTING.md', 'SECURITY.md', 'BUILD_VERIFICATION.md', '.gitignore', '.gitattributes',
)
FOLDERS = ('resources', 'licenses', 'tests', 'scripts', '.github', 'signing', 'openspec/specs')
INSTALLER_FILES = ('installer/PDFMaster.iss', 'installer/version.txt', 'installer/BUILD.md')
EXCLUDED_PARTS = {'.git', '.venv', 'venv', 'build', 'dist', 'qa', '.agents', '__pycache__',
                  '.pytest_cache', '.ci-tools', '.ci-env', 'node_modules', 'tools'}
PRIVATE_SUFFIXES = {'.pfx', '.p12', '.key', '.pem', '.log', '.pyc'}
MAX_FILE_BYTES = 95 * 1024 * 1024
TEXT_SUFFIXES = {'.py', '.ps1', '.md', '.txt', '.json', '.yaml', '.yml', '.xml', '.iss', '.spec', ''}
SECRET_PATTERNS = (
    re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----'),
    re.compile(r'(?<![A-Za-z0-9_])gh[pousr]_[A-Za-z0-9]{30,}'),
    re.compile(r'(?<![A-Za-z0-9_])github_pat_[A-Za-z0-9_]{30,}'),
)
PRIVATE_PATH = re.compile(r'(?<![A-Za-z0-9_/:])(?:[A-Za-z]:[\\/]+Users[\\/]+|/Users/|/home/)[^\s"\']+', re.I)


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _validate_file(path: Path, relative: Path):
    if path.is_symlink() or path.is_junction() or any(parent.is_symlink() or parent.is_junction() for parent in path.parents):
        raise ValueError(f'Symlinks are not publishable: {relative.as_posix()}')
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(f'File exceeds repository size limit: {relative.as_posix()}')
    if path.suffix.lower() in PRIVATE_SUFFIXES or path.name.startswith('.env'):
        raise ValueError(f'Private file is not publishable: {relative.as_posix()}')
    if path.suffix.lower() in TEXT_SUFFIXES:
        try:
            value = path.read_text(encoding='utf-8-sig')
        except UnicodeDecodeError:
            # Preserve legacy upstream notices, but still scan their ASCII secrets/paths.
            value = path.read_bytes().decode('latin-1')
        if any(pattern.search(value) for pattern in SECRET_PATTERNS):
            raise ValueError(f'Possible credential in: {relative.as_posix()}')
        # Patterns used by this scanner/tests are code, not developer paths.
        if relative.parts[0] not in ('tests', 'scripts') and PRIVATE_PATH.search(value):
            raise ValueError(f'Private absolute user path in: {relative.as_posix()}')


def collect_files(root: Path) -> list[Path]:
    root = Path(root).resolve()
    files = []
    for name in (*ROOT_FILES, *INSTALLER_FILES, 'openspec/config.yaml'):
        path = root / name
        if not path.is_file():
            raise ValueError(f'Required source file missing: {name}')
        files.append(path)
    for directory in (*FOLDERS, 'installer/hooks'):
        folder = root / directory
        if not folder.is_dir():
            raise ValueError(f'Required source directory missing: {directory}')
        for path in folder.rglob('*'):
            relative = path.relative_to(root)
            if EXCLUDED_PARTS.intersection(relative.parts):
                continue
            if path.is_file() or path.is_symlink():
                files.append(path)
    for path in files:
        _validate_file(path, path.relative_to(root))
    return sorted(set(files))


def _allowed_relative(relative: Path) -> bool:
    if relative.is_absolute() or '..' in relative.parts or EXCLUDED_PARTS.intersection(relative.parts):
        return False
    name = relative.as_posix()
    if name in (*ROOT_FILES, *INSTALLER_FILES, 'openspec/config.yaml'):
        return True
    return any(name.startswith(folder + '/') for folder in (*FOLDERS, 'installer/hooks'))


def check_repository(root: Path) -> dict:
    root = Path(root).resolve()
    manifest_file = root / 'repository-manifest.json'
    manifest = json.loads(manifest_file.read_text(encoding='utf-8'))
    expected = manifest['files']
    mandatory = set((*ROOT_FILES, *INSTALLER_FILES, 'openspec/config.yaml'))
    if not isinstance(expected, dict) or not mandatory.issubset(expected):
        raise ValueError('Mandatory public source files missing from manifest')
    for relative, record in expected.items():
        relative_path = Path(relative)
        if not _allowed_relative(relative_path):
            raise ValueError('Unsafe manifest path')
        path = root / relative_path
        if not path.is_file():
            raise ValueError(f'Missing published source: {relative}')
        _validate_file(path, relative_path)
        if path.stat().st_size != record['bytes'] or digest(path) != record['sha256']:
            raise ValueError(f'Source checksum mismatch: {relative}')
    actual = {p.relative_to(root).as_posix() for p in root.rglob('*')
              if p.is_file() and '.git' not in p.relative_to(root).parts
              and p.name != 'repository-manifest.json'}
    if actual != set(expected):
        raise ValueError('Unlisted files in public repository')
    return {'ok': True, 'files': len(expected), 'bytes': sum(row['bytes'] for row in expected.values())}


def prepare_repository(source: Path, destination: Path, initialize_git=False) -> dict:
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination == source or destination in source.parents or source in destination.parents:
        raise ValueError('Public export must be separate from the source tree')
    if destination.exists():
        raise FileExistsError('Destination already exists; choose a new export directory')
    files = collect_files(source)
    destination.mkdir(parents=True)
    records = {}
    for path in files:
        relative = path.relative_to(source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        if path.suffix.lower() in TEXT_SUFFIXES:
            try:
                target.write_text(path.read_text(encoding='utf-8-sig').replace('\r\n', '\n'), encoding='utf-8', newline='\n')
            except UnicodeDecodeError:
                pass
        records[relative.as_posix()] = {'bytes': target.stat().st_size, 'sha256': digest(target)}
    (destination / 'repository-manifest.json').write_text(json.dumps(
        {'project': 'PDF Master', 'version': '0.3.0', 'files': records}, ensure_ascii=False, indent=2), encoding='utf-8')
    report = check_repository(destination)
    if initialize_git:
        subprocess.run(['git', 'init', '--initial-branch=main', str(destination)], check=True, capture_output=True)
        subprocess.run(['git', '-C', str(destination), 'add', '--all'], check=True, capture_output=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--destination', type=Path)
    parser.add_argument('--check', type=Path)
    parser.add_argument('--init-git', action='store_true')
    args = parser.parse_args()
    if args.check:
        report = check_repository(args.check)
    elif args.destination:
        report = prepare_repository(args.source, args.destination, args.init_git)
    else:
        parser.error('Specify --destination or --check')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
