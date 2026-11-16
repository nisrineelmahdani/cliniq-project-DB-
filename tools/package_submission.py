"""Build an allowlisted, secret-checked academic submission without any DB access."""

import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import zipfile

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / 'submission' / 'CLINIQ_DEV009'
DIRECTORIES = ('database', 'db', 'services', 'pages', 'ui', 'tests', 'docs', 'tools')
ROOT_FILES = ('app.py', 'README.md', '.env.example', '.gitignore', 'requirements.txt',
              'requirements-dev.txt', 'requirements-validated.txt', 'pytest.ini', '.streamlit/config.toml')
SUFFIXES = {'.py', '.sql', '.md', '.json', '.png', '.css'}


def candidates() -> list[Path]:
    files = [ROOT / name for name in ROOT_FILES]
    for directory in DIRECTORIES:
        files.extend(path for path in (ROOT / directory).rglob('*')
                     if path.is_file() and path.suffix in SUFFIXES
                     and not any(part.startswith('.') or part == '__pycache__'
                                 for part in path.relative_to(ROOT).parts))
    for path in files:
        if path.is_symlink():
            raise ValueError('Submission refuses symlinks: ' + str(path.relative_to(ROOT)))
        if not path.is_file():
            raise ValueError('Required submission file missing: ' + str(path.relative_to(ROOT)))
    return sorted(set(files))


def scan(files: list[Path]) -> dict:
    # Only compare secret values in memory; never print or serialize them.
    secrets = [value for key, value in dotenv_values(ROOT / '.env').items()
               if value and len(value) >= 6 and any(word in key.upper()
                   for word in ('PASSWORD', 'SECRET', 'TOKEN', 'API_KEY'))]
    findings = []
    signatures = [r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
                  r'\bAKIA[A-Z0-9]{16}\b', r'\bgh[pousr]_[A-Za-z0-9]{30,}\b',
                  r'\bsk-proj-[A-Za-z0-9_-]{30,}\b']
    for path in files:
        if path.suffix == '.png':
            continue
        content = path.read_text(encoding='utf-8')
        if any(secret in content for secret in secrets):
            findings.append(str(path.relative_to(ROOT)) + ': configured secret value')
        if any(re.search(pattern, content) for pattern in signatures):
            findings.append(str(path.relative_to(ROOT)) + ': secret signature')
    git_result = subprocess.run(['git', 'ls-files', '-z'], cwd=ROOT, capture_output=True)
    tracked = git_result.stdout.decode().split('\0') if git_result.returncode == 0 else []
    tracked = [name for name in tracked if name]
    forbidden = [name for name in tracked if name == '.env' or name.endswith('secrets.toml')]
    if findings or forbidden:
        raise ValueError('Secret/file audit failed: ' + repr(findings + forbidden))
    return {'candidate_files_scanned': len(files), 'tracked_files': len(tracked),
            'git_metadata_available': git_result.returncode == 0,
            'configured_secret_matches': 0, 'secret_signature_matches': 0,
            'note': 'Best-effort signatures and exact configured secrets; not a proof against every possible secret. '
                    'Unit-test dummy credentials are fixtures, not real account secrets.'}


def main() -> None:
    files = candidates()
    audit = scan(files)  # All checks precede any output directory replacement.
    if DESTINATION.exists():
        # This fixed generated artifact directory alone is replaceable, never sources.
        if DESTINATION.is_symlink():
            raise ValueError('Refusing linked output directory')
        shutil.rmtree(DESTINATION)
    DESTINATION.mkdir(parents=True)
    manifest = {}
    for path in files:
        relative = path.relative_to(ROOT)
        target = DESTINATION / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        manifest[relative.as_posix()] = hashlib.sha256(target.read_bytes()).hexdigest()
    (DESTINATION / 'MANIFEST.sha256').write_text(
        ''.join(f'{digest}  {name}\n' for name, digest in sorted(manifest.items())), encoding='utf-8')
    (DESTINATION / 'PACKAGE_AUDIT.json').write_text(json.dumps(audit, indent=2) + '\n', encoding='utf-8')
    archive = DESTINATION.with_suffix('.zip')
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as output:
        for path in sorted(DESTINATION.rglob('*')):
            if path.is_file():
                output.write(path, arcname=path.relative_to(DESTINATION.parent))
    with zipfile.ZipFile(archive) as check:
        if check.testzip() is not None:
            raise ValueError('Archive integrity check failed')
    print(json.dumps({'directory': str(DESTINATION.relative_to(ROOT)),
                      'archive': str(archive.relative_to(ROOT)), 'source_files': len(files),
                      'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
                      'audit': audit}, indent=2))


if __name__ == '__main__':
    main()
