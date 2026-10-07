"""Host-side frontend transaction. Receives a ZIP on stdin; never deletes files."""
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import sys
import time
import urllib.request
import zipfile

ALLOWED = (
    'analytics.js', 'app.js', 'favicon.svg',
    'images/renpat-caja-cerrada-frente-480.webp',
    'images/renpat-caja-cerrada-frente-960.webp',
    'images/renpat-caja-cerrada-lateral-480.webp',
    'images/renpat-caja-cerrada-lateral-960.webp',
    'images/renpat-carga-en-operacion-480.webp',
    'images/renpat-carga-en-operacion-960.webp',
    'images/renpat-unidad-rl003-480.webp',
    'images/renpat-unidad-rl003-960.webp',
    'index.html', 'privacy.html', 'renpat-logo2-blue.svg',
    'robots.txt', 'sitemap.xml', 'social-card.svg', 'styles.css',
)
ORDER = sorted(ALLOWED, key=lambda name: (name.endswith('.html'), name))
MAX_BYTES = 25 * 1024 * 1024


def safe_directory(value):
    path = Path(value)
    if not path.is_absolute() or path != path.resolve() or not path.is_dir():
        raise ValueError('Directory must be existing, absolute and free of symlinks')
    return path


def check_target(root, name):
    path = root / name
    if path != path.resolve() or not path.is_file():
        raise ValueError('Every allowlisted target must already exist without symlinks: ' + name)
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError('Target must be a regular, single-link file: ' + name)
    return path


def unpack(payload):
    if len(payload) > MAX_BYTES:
        raise ValueError('Payload too large')
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or set(names) != set(ALLOWED) | {'manifest.json'}:
            raise ValueError('Payload must contain exactly the frontend allowlist and manifest')
        if sum(item.file_size for item in archive.infolist()) > MAX_BYTES:
            raise ValueError('Expanded payload too large')
        manifest = json.loads(archive.read('manifest.json'))
        if set(manifest) != set(ALLOWED):
            raise ValueError('Unexpected manifest')
        data = {name: archive.read(name) for name in ALLOWED}
        for name, content in data.items():
            if not content or hashlib.sha256(content).hexdigest() != manifest[name]:
                raise ValueError('Empty file or hash mismatch: ' + name)
        return data


def smoke(data, release):
    # No lead submission: only public read-only resources and config availability.
    for name in ('index.html', 'privacy.html', 'styles.css', 'app.js'):
        request = urllib.request.Request(
            'https://renpatlogistics.mx/' + name + '?deploy=' + release,
            headers={'Cache-Control': 'no-cache', 'User-Agent': 'RENPAT-deploy-check/1.0'},
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read(MAX_BYTES + 1)
            if response.status != 200 or body != data[name]:
                raise RuntimeError('Live content did not match: ' + name)
    for route in ('privacidad', 'api/config'):
        with urllib.request.urlopen('https://renpatlogistics.mx/' + route + '?deploy=' + release, timeout=20) as response:
            if response.status != 200:
                raise RuntimeError('Live route unavailable: ' + route)
            body = response.read(MAX_BYTES + 1)
            if route == 'api/config' and (len(body) > 65536 or not isinstance(json.loads(body), dict)):
                raise RuntimeError('Config endpoint must return a bounded JSON object')
            if route == 'privacidad' and body != data['privacy.html']:
                raise RuntimeError('Privacy route did not return the deployed privacy page')


def replace_file(source, target, mode):
    # source and target are on one filesystem; rename is atomic for each file.
    os.chmod(source, mode)
    os.replace(source, target)


def restore(root, release_dir):
    for name in ORDER:
        target = check_target(root, name)
        source = release_dir / 'before' / name
        if not source.is_file() or source.is_symlink():
            raise ValueError('Invalid rollback backup: ' + name)
        tmp = release_dir / 'restore' / name
        tmp.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, tmp)
        replace_file(tmp, target, stat.S_IMODE(source.stat().st_mode))


def transact(root_value, backup_value, release, payload, checker=smoke):
    root, backup = safe_directory(root_value), safe_directory(backup_value)
    if root == backup or root in backup.parents or backup in root.parents:
        raise ValueError('Backup directory must be separate from and outside the document root')
    if root.stat().st_dev != backup.stat().st_dev:
        raise ValueError('Staging and document root must share a filesystem')
    if stat.S_IMODE(backup.stat().st_mode) & 0o077:
        raise ValueError('Private backup directory must have mode 700')
    if not re.fullmatch(r'[0-9a-f]{40}-[0-9]+-[0-9]+', release):
        raise ValueError('Invalid release ID')
    data = unpack(payload)
    lock_path = backup / 'deploy.lock'
    if lock_path.is_symlink():
        raise ValueError('Unsafe lock path')
    with lock_path.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for prior in backup.iterdir():
            if prior.is_dir():
                state_file = prior / 'status.json'
                if not state_file.is_file() or json.loads(state_file.read_text()).get('state') not in ('verified', 'rolled-back'):
                    raise RuntimeError('Prior deployment is incomplete; inspect and restore before continuing')
        release_dir = backup / release
        release_dir.mkdir(mode=0o700)  # Never reuse a release or overwrite a backup.
        modes = {}
        for name in ALLOWED:
            target = check_target(root, name)
            modes[name] = stat.S_IMODE(target.stat().st_mode)
            for folder in ('before', 'staged'):
                (release_dir / folder / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, release_dir / 'before' / name)
            (release_dir / 'staged' / name).write_bytes(data[name])
        required_free = 2 * sum(len(content) for content in data.values()) + 64 * 1024 * 1024
        if shutil.disk_usage(backup).free < required_free:
            raise RuntimeError('Insufficient free space for safe frontend restoration')
        record = {'release': release, 'root': str(root), 'files': list(ALLOWED), 'state': 'backed-up'}
        status = release_dir / 'status.json'
        status.write_text(json.dumps(record))
        try:
            for name in ORDER:
                target = check_target(root, name)
                replace_file(release_dir / 'staged' / name, target, modes[name])
            # Cached content can lag briefly; no new transfer occurs during retries.
            for attempt in range(3):
                try:
                    checker(data, release)
                    break
                except Exception:
                    if attempt == 2:
                        raise
                    time.sleep(5)
            record['state'] = 'verified'
            status.write_text(json.dumps(record))
            print('Frontend deployed and read-only live checks passed. Backup: ' + release)
        except BaseException:
            # Reporting failures must never prevent restoration.
            record['state'] = 'rollback-started'
            try:
                status.write_text(json.dumps(record))
            except OSError:
                pass
            restore(root, release_dir)
            record['state'] = 'rolled-back'
            try:
                status.write_text(json.dumps(record))
            except OSError:
                pass
            print('Deployment failed; prior frontend restored. Backup retained: ' + release, file=sys.stderr)
            raise


if __name__ == '__main__':
    if len(sys.argv) != 4:
        raise SystemExit('Expected document root, private backup directory, release ID')
    def interrupted(signum, frame):
        raise SystemExit('Deployment interrupted by signal ' + str(signum))
    for sig in (signal.SIGHUP, signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    transact(*sys.argv[1:], sys.stdin.buffer.read(MAX_BYTES + 1))
