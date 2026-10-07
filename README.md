# RENPAT Logistics website

Public-facing frontend snapshot for https://renpatlogistics.mx, captured October 7, 2026.

## Contents

`public_html/` contains the deployed HTML, CSS, JavaScript, logos, SEO files, and eight responsive website image files. Paths and frontend behavior are preserved.

This is **not a complete application or server backup**. Backend source, hosting configuration (including `.htaccess`), credentials, environment files, customer records, and lead data are not included.

## Local preview

Serve `public_html/` with a local static web server. The homepage can be previewed, but the production `/privacidad` route needs a server rewrite to `privacy.html` (or visit `/privacy.html` locally).

The quote form depends on the existing server's `/api/config` and `/api/leads` endpoints. Those endpoints are not implemented in this repository. A static preview alone cannot receive quote requests.

## Frontend checks and deployment

GitHub Actions checks frontend changes. Production deployment is gated off until the secure Hostinger connection and controlled live test are complete. See [DEPLOYMENT.md](DEPLOYMENT.md) for the setup status, explicit file scope, activation and rollback instructions.

Existing server APIs, `.htaccess`, PHP files, private configuration and customer data are deliberately outside deployment scope. Do not use a destructive directory sync.

Do not upload secrets, private configuration, customer data, server backups, or logs to this repository.
