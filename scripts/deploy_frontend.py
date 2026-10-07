"""Validated frontend upload over host-key-pinned OpenSSH. No remote deletion."""
import io
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import zipfile
from validate_frontend import validate


def main():
    names = ('DEPLOY_HOST', 'DEPLOY_PORT', 'DEPLOY_USER', 'DEPLOY_ROOT',
             'DEPLOY_BACKUP_ROOT', 'DEPLOY_KEY_FILE', 'DEPLOY_KNOWN_HOSTS_FILE',
             'GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT')
    config = {name: os.environ.get(name, '') for name in names}
    if not all(config.values()):
        raise SystemExit('Deployment setup incomplete; missing required configuration')
    if not re.fullmatch(r'[A-Za-z0-9.-]+', config['DEPLOY_HOST']):
        raise SystemExit('Invalid SSH host')
    if not re.fullmatch(r'[A-Za-z0-9_]+', config['DEPLOY_USER']):
        raise SystemExit('Invalid SSH user')
    port = int(config['DEPLOY_PORT'])
    if not 1 <= port <= 65535:
        raise SystemExit('Invalid SSH port')
    for name in ('DEPLOY_ROOT', 'DEPLOY_BACKUP_ROOT'):
        if not config[name].startswith('/') or '\n' in config[name]:
            raise SystemExit('Use independently verified absolute server directories')
    here = Path(__file__).resolve().parent
    root = here.parent / 'public_html'
    manifest = validate(root)
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('manifest.json', json.dumps(manifest))
        for name in manifest:
            archive.write(root / name, name)
    release = '-'.join(config[name] for name in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'))
    remote = ['python3', '-c', (here / 'remote_deploy.py').read_text(),
              config['DEPLOY_ROOT'], config['DEPLOY_BACKUP_ROOT'], release]
    command = ['ssh', '-T', '-p', str(port), '-i', config['DEPLOY_KEY_FILE'],
               '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes',
               '-o', 'StrictHostKeyChecking=yes',
               '-o', 'UserKnownHostsFile=' + config['DEPLOY_KNOWN_HOSTS_FILE'],
               '-o', 'ConnectTimeout=15', '-o', 'ServerAliveInterval=15',
               '-o', 'ServerAliveCountMax=4',
               config['DEPLOY_USER'] + '@' + config['DEPLOY_HOST'], shlex.join(remote)]
    subprocess.run(command, input=payload.getvalue(), check=True)


if __name__ == '__main__':
    main()
