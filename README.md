# RENPAT Logistics website

Public-facing frontend snapshot for https://renpatlogistics.mx, captured October 7, 2026.

## Contents

`public_html/` contains the deployed HTML, CSS, JavaScript, logos, SEO files, and four website images. Paths and frontend behavior are preserved.

This is **not a complete application or server backup**. Backend source, hosting configuration (including `.htaccess`), credentials, environment files, customer records, and lead data are not included.

## Local preview

Serve `public_html/` with a local static web server. The homepage can be previewed, but the production `/privacidad` route needs a server rewrite to `privacy.html` (or visit `/privacy.html` locally).

The quote form depends on the existing server's `/api/config` and `/api/leads` endpoints. Those endpoints are not implemented in this repository. A static preview alone cannot receive quote requests.

## Manual deployment

There is no automatic deployment configured in this repository. Review changes, back up the current public frontend files, then manually upload the contents of `public_html/` into the site's existing public document root using the hosting provider's supported method. Preserve the existing backend, server routing, `.htaccess`, and private configuration. Verify the homepage, privacy route, images, and quote form on the live domain after deployment.

Do not upload secrets, private configuration, customer data, server backups, or logs to this repository.
