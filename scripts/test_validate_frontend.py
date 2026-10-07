"""Offline validation regression tests: python -m unittest discover -s scripts."""

import hashlib
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from validate_frontend import ALLOWED, MAX_TEXT_BYTES, ValidationError, validate


class FrontendValidationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "public_html"
        self.root.mkdir()
        for name in ALLOWED:
            path = self.root / name
            path.parent.mkdir(exist_ok=True)
            if name.endswith(".webp"):
                path.write_bytes(b"RIFF\x04\x00\x00\x00WEBP")
            elif name.endswith(".svg"):
                path.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
            elif name.endswith(".html"):
                path.write_text(self.html('<a href="/privacidad">Privacidad</a>'))
            elif name.endswith(".xml"):
                path.write_text('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                                '<url><loc>https://renpatlogistics.mx/</loc></url>'
                                '<url><loc>https://renpatlogistics.mx/privacidad</loc></url></urlset>')
            elif name == "app.js":
                path.write_text("fetch('/api/config'); fetch('/api/leads');\n")
            elif name.endswith(".js"):
                path.write_text("'use strict';\n")
            elif name.endswith(".css"):
                path.write_text("body { color: #123; }\n")
            else:
                path.write_text("User-agent: *\nDisallow: /api/\n")

    @staticmethod
    def html(body):
        return '<!doctype html><html><head><title>Test</title></head><body>' + body + '</body></html>'

    def write(self, name, text):
        (self.root / name).write_text(text, encoding="utf-8")

    def assert_rejected(self, fragment):
        with self.assertRaisesRegex(ValidationError, fragment):
            validate(self.root)

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for the happy path")
    def test_happy_snapshot_has_exact_sha256_manifest(self):
        manifest = validate(self.root)
        self.assertEqual(tuple(manifest), ALLOWED)
        self.assertEqual(len(manifest), 18)
        for name, checksum in manifest.items():
            self.assertEqual(checksum, hashlib.sha256((self.root / name).read_bytes()).hexdigest())

    def test_extra_backend_config_and_secret_files_rejected(self):
        for name in ("server.php", ".env", ".htaccess", "config.json", "backup.zip", "leads.csv"):
            with self.subTest(name=name):
                self.write(name, "private content")
                self.assert_rejected("Unexpected file")
                (self.root / name).unlink()

    def test_unexpected_empty_directory_rejected(self):
        (self.root / "api").mkdir()
        self.assert_rejected("Unexpected directory")

    def test_missing_file_rejected(self):
        (self.root / "app.js").unlink()
        self.assert_rejected("Missing files: app.js")

    def test_empty_file_rejected(self):
        self.write("index.html", "")
        self.assert_rejected("Empty file: index.html")

    def test_oversized_file_rejected_before_read(self):
        with (self.root / "app.js").open("wb") as stream:
            stream.truncate(MAX_TEXT_BYTES + 1)
        self.assert_rejected("Oversized file: app.js")

    def test_total_size_limit_enforced(self):
        with mock.patch("validate_frontend.MAX_TOTAL_BYTES", 10):
            self.assert_rejected("exceeds")

    def test_symlink_file_rejected(self):
        (self.root / "app.js").unlink()
        (self.root / "app.js").symlink_to(self.root / "analytics.js")
        self.assert_rejected("Symlink is forbidden: app.js")

    def test_broken_symlink_rejected(self):
        (self.root / "secret.txt").symlink_to(self.root / "missing")
        self.assert_rejected("Symlink is forbidden")

    def test_symlink_directory_rejected(self):
        shutil.rmtree(self.root / "images")
        outside = Path(self.temporary.name) / "outside"
        outside.mkdir()
        (self.root / "images").symlink_to(outside, target_is_directory=True)
        self.assert_rejected("Symlink is forbidden: images")

    def test_symlink_root_rejected(self):
        alias = Path(self.temporary.name) / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValidationError, "root and its parents"):
            validate(alias)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "Requires POSIX FIFOs")
    def test_nonregular_file_rejected_without_opening(self):
        (self.root / "app.js").unlink()
        os.mkfifo(self.root / "app.js")
        self.assert_rejected("Only regular files")

    def test_private_key_inside_allowed_file_rejected(self):
        self.write("analytics.js", "// -----BEGIN PRIVATE KEY-----\n")
        self.assert_rejected("Forbidden private key")

    def test_literal_secret_inside_allowed_file_rejected(self):
        self.write("analytics.js", 'const client_secret = "not-a-real-secret";')
        self.assert_rejected("Forbidden literal credential")

    def test_server_code_inside_allowed_file_rejected(self):
        self.write("index.html", self.html("<?php echo 'unsafe'; ?>"))
        self.assert_rejected("Forbidden server-side code")

    def test_non_utf8_text_rejected(self):
        (self.root / "styles.css").write_bytes(b"\xff")
        self.assert_rejected("Invalid UTF-8")

    def test_bad_image_signature_rejected(self):
        self.write("images/renpat-unidad-rl003-960.webp", "<html>Error page</html>")
        self.assert_rejected("Invalid WebP")

    def test_broken_html_reference_rejected(self):
        self.write("index.html", self.html('<img src="/missing.webp?v=1">'))
        self.assert_rejected("missing/non-allowlisted 'missing.webp'")

    def test_broken_srcset_candidate_rejected_even_with_valid_src(self):
        self.write("index.html", self.html(
            '<img src="/images/renpat-unidad-rl003-960.webp" '
            'srcset="/images/renpat-unidad-rl003-320.webp 480w, '
            '/images/renpat-unidad-rl003-960.webp 960w">'))
        self.assert_rejected("renpat-unidad-rl003-320.webp")

    @unittest.skipUnless(shutil.which("node"), "Node.js is required")
    def test_existing_local_relative_absolute_query_and_api_references(self):
        self.write("index.html", self.html(
            '<link href="styles.css?v=1"><script src="/app.js"></script>'
            '<a href="/privacidad#contenido">Privacy</a><a href="/#section">Home</a>'
            '<a href="https://renpatlogistics.mx/privacy.html">Same site</a>'
            '<a href="//renpatlogistics.mx/">Home</a>'
            '<form action="/api/leads"><button formaction="/api/config">Go</button></form>'
            '<img srcset="/favicon.svg 1x, /social-card.svg 2x" src="/favicon.svg">'))
        self.assertEqual(len(validate(self.root)), len(ALLOWED))

    @unittest.skipUnless(shutil.which("node"), "Node.js is required")
    def test_external_mail_tel_and_data_urls_do_not_require_local_files(self):
        self.write("index.html", self.html(
            '<a href="https://example.org/missing">External</a><a href="//example.org/x">X</a>'
            '<a href="mailto:info@example.org">Email</a><a href="tel:+15550000000">Phone</a>'
            '<img src="data:image/png;base64,AA==" '
            'srcset="data:image/png;base64,AA== 1x, /favicon.svg 2x">'))
        validate(self.root)

    def test_same_origin_absolute_missing_reference_rejected(self):
        self.write("index.html", self.html('<img src="https://renpatlogistics.mx/missing.svg">'))
        self.assert_rejected("missing.svg")

    def test_unapproved_server_route_rejected(self):
        self.write("index.html", self.html('<form action="/api/admin"></form>'))
        self.assert_rejected("api/admin")

    def test_traversal_and_unsafe_url_schemes_rejected(self):
        for url in ("../secret", "/%2e%2e/secret", "/%252e%252e/secret", "file:///etc/passwd",
                    "javascript:alert(1)", "/%5csecret", "/%00secret"):
            with self.subTest(url=url):
                self.write("index.html", self.html(f'<img src="{url}">'))
                self.assert_rejected("URL|traversal|encoding")

    def test_html_base_rejected(self):
        self.write("index.html", self.html('<base href="https://example.org/">'))
        self.assert_rejected("base")

    def test_incomplete_html_rejected(self):
        self.write("index.html", "Error loading site")
        self.assert_rejected("Incomplete HTML")

    def test_broken_css_reference_rejected(self):
        for css in ('body { background: url("missing.svg"); }',
                    "body { background: URL(missing.svg); }", "@import 'missing.css';",
                    r"body { background: url('\6d issing.svg'); }"):
            with self.subTest(css=css):
                self.write("styles.css", css)
                self.assert_rejected("missing/non-allowlisted")

    def test_inline_style_reference_rejected(self):
        self.write("index.html", self.html('<div style="background:url(/missing.svg)"></div>'))
        self.assert_rejected("missing.svg")

    def test_style_element_reference_rejected(self):
        self.write("index.html", self.html('<style>body { background:url(/missing.svg) }</style>'))
        self.assert_rejected("missing.svg")

    @unittest.skipUnless(shutil.which("node"), "Node.js is required")
    def test_css_comments_strings_fragments_and_data_urls(self):
        self.write("styles.css", '/* url(missing.png) */ .a { content: "url(missing.png)";'
                   'background: url(/favicon.svg?v=1); mask: url(#local); }'
                   '.b { background: url("data:image/svg+xml;base64,AA=="); }')
        validate(self.root)

    def test_invalid_xml_and_svg_rejected(self):
        for name in ("sitemap.xml", "favicon.svg"):
            with self.subTest(name=name):
                original = (self.root / name).read_text()
                self.write(name, "<broken>")
                self.assert_rejected("Invalid XML")
                self.write(name, original)

    def test_wrong_xml_root_rejected(self):
        self.write("favicon.svg", "<html/>")
        self.assert_rejected("Unexpected XML root/namespace")

    def test_xml_entities_rejected(self):
        self.write("favicon.svg", '<!DOCTYPE svg [<!ENTITY file SYSTEM "file:///etc/passwd">]>'
                   '<svg xmlns="http://www.w3.org/2000/svg">&file;</svg>')
        self.assert_rejected("DTD/entity")

    def test_svg_local_reference_rejected(self):
        self.write("favicon.svg", '<svg xmlns="http://www.w3.org/2000/svg">'
                   '<image href="missing.webp"/></svg>')
        self.assert_rejected("missing.webp")

    def test_sitemap_local_reference_rejected(self):
        self.write("sitemap.xml", '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                   '<url><loc>https://renpatlogistics.mx/gone</loc></url></urlset>')
        self.assert_rejected("gone")

    def test_api_endpoint_contract_preserved(self):
        self.write("app.js", "fetch('/api/config'); fetch('/new-leads');")
        self.assert_rejected("must preserve the existing endpoint /api/leads")

    @unittest.skipUnless(shutil.which("node"), "Node.js is required")
    def test_javascript_syntax_checked_without_execution(self):
        self.write("analytics.js", "throw new Error('This must never execute');")
        validate(self.root)
        self.write("analytics.js", "const broken = ;")
        self.assert_rejected("JavaScript syntax check failed: analytics.js")

    def test_missing_node_fails_closed(self):
        with mock.patch("validate_frontend.shutil.which", return_value=None):
            self.assert_rejected("Node.js is required")


if __name__ == "__main__":
    unittest.main()
