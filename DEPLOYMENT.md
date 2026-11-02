# Frontend deployment setup

## Status

Automatic publishing is active as of November 1, 2026. Every push to `main` runs
frontend checks and deploys the latest main commit after they pass. Superseded
commits are skipped. Pull requests run checks only. The repository variable
`RENPAT_DEPLOY_READY` is `true`; setting it to `false` disables production transfer.
The `production` environment is restricted to branch `main`.

On November 1, 2026, the existing dedicated SSH connection authenticated with
strict host-key checking against the hPanel-verified pinned key. Python 3 and
`fcntl` are available. The verified document root is
`/home/u421832739/domains/renpatlogistics.mx/public_html`. All 18 allowlisted
files are regular, canonical, single-link files and match this checkout byte for
byte. The homepage, `/privacidad` and `/api/config` returned HTTP 200; config
returned a JSON object. No lead was submitted.

The GitHub `production` environment has been created and restricted to branch
`main`. A private mode-700 backup directory was created and verified on the same
filesystem at `/home/u421832739/domains/renpatlogistics.mx/.renpat-deploy`.
All five connection/path variables and both encrypted deployment secrets are
configured in that environment using the existing dedicated key and pinned host
entry. The user explicitly approved persistent GitHub deployment access and the
controlled first transfer. The key authenticates as the hosting account; the
18-file limit is enforced by this reviewed workflow, not an SSH account sandbox.

The [controlled first run](https://github.com/renatto-tommasi/renpat-logistics-website/actions/runs/41393632169)
completed successfully: checks and transfer passed, including read-only live byte
comparison and route checks. Its release ID is
`6ffdd52001d25735600edbb492182c8816e8ca80-41393632169-1`.
Host-side status was independently read back as `verified`; the mode-700 backup
contains all 18 prior files, matching the deployed frontend. Failure restoration
was validated locally with injected transfer, smoke-check and termination failures;
no deliberate failure was injected into production.

## Scope and safeguards

- Only the explicit 18 frontend paths in `scripts/validate_frontend.py` and `scripts/remote_deploy.py` can be transferred. Adding/removing a file requires reviewing both allowlists and the deployment baseline. Every current frontend target must already exist before the first mutation.
- `.htaccess`, `api.php`, `default.php`, API routes, server settings, logs, private directories, lead/customer data and any untracked server file are untouched. There is no remote delete or mirror operation.
- Local checks reject extra files, missing assets and unsafe paths, and check syntax and references. Checks have no production credentials on pull requests.
- OpenSSH uses strict known-host validation. Never use `StrictHostKeyChecking=no`, automatic trust of `ssh-keyscan` output, or passwords in commands.
- A separate private mode-700 backup/staging directory must be outside the public document root on the same filesystem. Complete backups precede changes. Individual files are replaced atomically, assets first and HTML last. The whole site is not an atomic transaction; a brief old-HTML/new-asset interval is possible.
- A host-side lock and GitHub concurrency prevent simultaneous deployments. In-progress deployment runs are not canceled automatically. Never manually cancel a transfer unless required to stop a security incident.
- Read-only live checks compare deployed HTML/CSS/JS bytes and verify `/privacidad` and `/api/config`. No quote/lead is submitted. Failure rolls back the prior frontend. Full form delivery is a separate, explicitly authorized test.
- Backups remain private on the host, not in GitHub artifacts. No automatic backup deletion. Monitor storage and review retention manually.

## Required secure setup

1. Obtain action-time approval before enabling Hostinger SSH or creating/configuring persistent deployment access. Account-wide SSH may expose other sites/private files; confirm the effective scope and use a dedicated restricted deployment identity where supported.
2. Independently verify the server host key through a trusted Hostinger channel. A network `ssh-keyscan` alone does not authenticate the host. Have the user enter the private deployment key directly in GitHub's secure secret UI; never put it in chat, source control, screenshots, logs or a URL. Creating a key, adding its public key on Hostinger, and configuring its persistent access require explicit approval.
3. Verify the exact absolute document root, available Python 3 and `fcntl`, same-filesystem private backup directory, and all 18 existing targets. Create a private backup directory only with authorization for the host change. The script refuses symlinked directories/files, hard-linked targets or backup directories under the webroot.
4. Use a GitHub environment named `production` with the following configuration. Leave readiness unset until controlled activation. Restrict deployment branches to `main` and review who can edit workflows/access credentials; changing access protections requires appropriate approval.

Repository variable:

- `RENPAT_DEPLOY_READY`: initially unset or `false`. This must be a repository variable because the job-level gate runs before environment variables are available.

Production environment variables:

- `RENPAT_SSH_HOST`: verified host
- `RENPAT_SSH_PORT`: verified SSH port
- `RENPAT_SSH_USER`: authorized deployment account
- `RENPAT_DOCUMENT_ROOT`: verified absolute `public_html` directory
- `RENPAT_BACKUP_ROOT`: verified absolute, private, separate mode-700 directory

Production environment secrets, entered through secure settings:

- `RENPAT_SSH_PRIVATE_KEY`: dedicated deployment key
- `RENPAT_SSH_KNOWN_HOSTS`: independently verified known_hosts entry, including `[host]:port` for a nonstandard SSH port

5. Run the checks first. After setup is reviewed and activation is authorized, set readiness to `true` and use **Run workflow** on `main` for the controlled first transfer. Watch the exact run to completion and inspect the live homepage, privacy route and images. Any setup/test failure means automatic deployment is not yet verified; turn readiness back to `false` while investigating.
6. Subsequent pushes to `main` then deploy only after checks pass. Pull requests never deploy. Avoid concurrent out-of-band hosting edits during a release.

## Failure and rollback

Normal transfer or smoke-check failures restore every allowlisted frontend file from that release's `before/` backup. A failed connection before transfer changes no production files. Handled hangup/termination signals trigger restoration. Uncatchable termination (such as SIGKILL or host power loss) or a failed restoration can leave the outcome uncertain: inspect the host's private `<release>/status.json` and live content before retrying. The next deployment refuses to continue when a prior release has no final verified/rolled-back status. Do not automatically retry an uncertain transfer.

For a deliberate later rollback, prefer reverting the frontend change in GitHub and letting checks redeploy it. For emergency manual restoration, copy only the 18 files from the chosen private `<release>/before/` directory into the verified document root, assets first and HTML last, preserving permissions. Do not copy the backup directory itself into `public_html`, restore unrelated server files, or delete extra production files. The backup records the frontend that existed immediately before that release.

## Local checks

Run from the repository root:

    python3 -m unittest discover -s scripts -p 'test_*.py' -v
    python3 scripts/validate_frontend.py

Python 3 and Node.js are required; no extra Python/npm packages are installed. Deployment also needs the system OpenSSH client and host-side Python 3. The GitHub workflow uses an immutable checkout action commit and read-only repository token permissions.
