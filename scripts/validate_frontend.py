#!/usr/bin/env python3
"""Fail-closed checks for the deliberately small RENPAT public frontend.

Python's standard library and Node.js are the only requirements. This checks
static references and JavaScript syntax, not live API behavior or browser layout.
The allowlist is also the deployment script's source of truth: do not derive it
from whatever happens to be in public_html.
"""

from __future__ import annotations

import argparse
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET


ALLOWED = (
    "analytics.js",
    "app.js",
    "favicon.svg",
    "images/renpat-caja-cerrada-frente-480.webp",
    "images/renpat-caja-cerrada-frente-960.webp",
    "images/renpat-caja-cerrada-lateral-480.webp",
    "images/renpat-caja-cerrada-lateral-960.webp",
    "images/renpat-carga-en-operacion-480.webp",
    "images/renpat-carga-en-operacion-960.webp",
    "images/renpat-unidad-rl003-480.webp",
    "images/renpat-unidad-rl003-960.webp",
    "index.html",
    "privacy.html",
    "renpat-logo2-blue.svg",
    "robots.txt",
    "sitemap.xml",
    "social-card.svg",
    "styles.css",
)
ALLOWED_DIRS = {"images"}
MAX_TEXT_BYTES = 2 * 1024 * 1024
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_TOTAL_BYTES = 16 * 1024 * 1024
SITE_HOSTS = {"renpatlogistics.mx", "www.renpatlogistics.mx"}
SERVER_ROUTES = {"/api/config", "/api/leads"}
HTML_ROUTES = {"/": "index.html", "/privacidad": "privacy.html"}
SVG_NAMESPACE = "http://www.w3.org/2000/svg"
SITEMAP_NAMESPACE = "http://www.sitemaps.org/schemas/sitemap/0.9"
_SECRET_PATTERNS = (
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----")),
    ("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("GitHub token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,})\b")),
    ("literal credential", re.compile(
        r"\b(?:password|passwd|db_password|client_secret|api_secret|secret_key|access_token|refresh_token)"
        r"[\"']?\s*[:=]\s*[\"'][^\"'\r\n]{8,}[\"']", re.I)),
    ("server-side code", re.compile(r"<\?(?:php|=)|<%[=@]?", re.I)),
)


class ValidationError(ValueError):
    """An unsafe or incomplete frontend must not be deployed."""


def _read_files(root: Path) -> dict[str, bytes]:
    root = root.absolute()
    if root.is_symlink() or any(parent.is_symlink() for parent in root.parents):
        raise ValidationError("The frontend root and its parents must not be symlinks")
    if not root.is_dir():
        raise ValidationError(f"Frontend directory does not exist: {root}")

    found: set[str] = set()
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in sorted(dirs + files):
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                raise ValidationError(f"Symlink is forbidden: {relative}")
            if stat.S_ISDIR(mode):
                if relative not in ALLOWED_DIRS:
                    raise ValidationError(f"Unexpected directory: {relative}")
            elif not stat.S_ISREG(mode):
                raise ValidationError(f"Only regular files are allowed: {relative}")
            elif relative not in ALLOWED:
                raise ValidationError(f"Unexpected file (backend, secrets and config are excluded): {relative}")
            else:
                found.add(relative)

    missing = set(ALLOWED) - found
    if missing:
        raise ValidationError("Missing files: " + ", ".join(sorted(missing)))

    contents = {}
    total = 0
    for relative in ALLOWED:
        limit = MAX_IMAGE_BYTES if relative.endswith(".webp") else MAX_TEXT_BYTES
        path = root / relative
        # O_NOFOLLOW closes the final-component symlink race where supported.
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise ValidationError(f"Only regular files are allowed: {relative}")
            if info.st_size == 0:
                raise ValidationError(f"Empty file: {relative}")
            if info.st_size > limit:
                raise ValidationError(f"Oversized file: {relative} (maximum {limit} bytes)")
            data = stream.read(limit + 1)
        if not data or len(data) > limit or len(data) != info.st_size:
            raise ValidationError(f"File changed or has an invalid size: {relative}")
        total += len(data)
        if total > MAX_TOTAL_BYTES:
            raise ValidationError(f"Frontend exceeds {MAX_TOTAL_BYTES} bytes in total")
        contents[relative] = data
    return contents


def _local_target(source: str, value: str) -> str | None:
    """Resolve one URL without accessing the network or the host filesystem."""
    value = value.strip()
    if any(ord(char) < 32 for char in value):
        raise ValidationError(f"{source}: control character in URL")
    if "\\" in value:
        raise ValidationError(f"{source}: backslash in URL is not supported")
    try:
        parts = urlsplit(value)
    except ValueError as error:
        raise ValidationError(f"{source}: malformed URL") from error
    if parts.scheme and parts.scheme.lower() not in {"http", "https", "mailto", "tel", "data"}:
        raise ValidationError(f"{source}: unsupported URL scheme {parts.scheme!r}")
    if parts.scheme.lower() in {"mailto", "tel", "data"}:
        return None
    if parts.netloc and parts.hostname not in SITE_HOSTS:
        return None
    path = unquote(parts.path, errors="strict")
    if "\\" in path or "\x00" in path or any(ord(char) < 32 for char in path):
        raise ValidationError(f"{source}: unsafe encoded URL path")
    if re.search(r"%[0-9a-f]{2}", path, re.I):
        raise ValidationError(f"{source}: nested URL encoding is not supported")
    if ".." in path.split("/"):
        raise ValidationError(f"{source}: parent traversal in local URL")
    if not path:
        return "index.html" if parts.netloc else source
    if path in SERVER_ROUTES:
        return None
    if path in HTML_ROUTES:
        return HTML_ROUTES[path]
    if path.startswith("/"):
        target = PurePosixPath(path.lstrip("/"))
    else:
        target = PurePosixPath(source).parent / path
    return str(target)


def _srcset_urls(value: str):
    """Read HTML srcset candidates, preserving commas inside data URLs."""
    remaining = value
    while remaining:
        remaining = remaining.lstrip(" \t\r\n\f,")
        if not remaining:
            return
        match = re.match(r"[^\s]+", remaining)
        assert match is not None
        token = match.group()
        remaining = remaining[len(token):]
        yield token.rstrip(",")
        if token.endswith(","):
            continue
        # A descriptor may contain parentheses in future syntax; commas inside
        # them are not candidate delimiters.
        depth = 0
        for index, char in enumerate(remaining):
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            elif char == "," and depth == 0:
                remaining = remaining[index + 1:]
                break
        else:
            remaining = ""


def _css_unescape(value: str) -> str:
    def replace(match):
        escaped = match.group(1)
        if re.fullmatch(r"[0-9a-fA-F]{1,6}\s?", escaped):
            codepoint = int(escaped.strip(), 16)
            if codepoint == 0 or codepoint > 0x10FFFF:
                raise ValidationError("Invalid CSS escape")
            return chr(codepoint)
        return "" if escaped in {"\n", "\r", "\r\n"} else escaped
    return re.sub(r"\\([0-9a-fA-F]{1,6}\s?|\r\n|[\s\S])", replace, value)


def _css_urls(css: str):
    # Consume comments and quoted strings as tokens, so their apparent url(...)
    # contents cannot masquerade as real references. Also support @import "...".
    token = re.compile(
        r"/\*[\s\S]*?\*/|(?P<url>url\s*\(\s*(?:\"(?:\\[\s\S]|[^\"\\])*\"|'(?:\\[\s\S]|[^'\\])*'|(?:\\[\s\S]|[^)\\])*)\s*\))"
        r"|(?P<import>@import\s+(?:\"(?:\\[\s\S]|[^\"\\])*\"|'(?:\\[\s\S]|[^'\\])*'))"
        r"|\"(?:\\[\s\S]|[^\"\\])*\"|'(?:\\[\s\S]|[^'\\])*'", re.I)
    for match in token.finditer(css):
        if match.group("url"):
            value = match.group()[match.group().index("(") + 1:-1].strip()
        elif match.group("import"):
            value = re.sub(r"^@import\s+", "", match.group(), flags=re.I)
        else:
            continue
        if value[:1] in {"'", '"'}:
            value = value[1:-1]
        yield _css_unescape(value)


class _HTMLReferences(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.references: list[str] = []
        self.css: list[str] = []
        self.tags: set[str] = set()
        self.in_style = False

    def handle_starttag(self, tag, attrs):
        self.tags.add(tag)
        if tag == "base":
            raise ValidationError("HTML <base> is not supported; use explicit site paths")
        if tag == "style":
            self.in_style = True
        attributes = dict(attrs)
        for name, value in attrs:
            if value is None:
                continue
            if name in {"href", "src", "poster", "action", "formaction", "background", "xlink:href"}:
                self.references.append(value)
            elif name == "data" and tag == "object":
                self.references.append(value)
            elif name in {"srcset", "imagesrcset"}:
                self.references.extend(_srcset_urls(value))
            elif name == "style":
                self.css.append(value)
        if tag == "meta" and (attributes.get("property", "").lower() in {"og:image", "og:url"}
                              or attributes.get("name", "").lower() in {"twitter:image"}):
            self.references.append(attributes.get("content", ""))

    def handle_endtag(self, tag):
        if tag == "style":
            self.in_style = False

    def handle_data(self, data):
        if self.in_style:
            self.css.append(data)


def validate(root: Path) -> dict[str, str]:
    """Return a stable SHA-256 manifest, or raise ValidationError before deploy."""
    contents = _read_files(Path(root))
    texts = {}
    for relative, data in contents.items():
        if relative.endswith(".webp"):
            if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
                raise ValidationError(f"Invalid WebP signature: {relative}")
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValidationError(f"Invalid UTF-8: {relative}") from error
        if "\x00" in text:
            raise ValidationError(f"NUL byte in text file: {relative}")
        for label, pattern in _SECRET_PATTERNS:
            if pattern.search(text):
                raise ValidationError(f"Forbidden {label} detected in {relative}")
        texts[relative] = text

    references: list[tuple[str, str]] = []
    for relative, text in texts.items():
        suffix = PurePosixPath(relative).suffix
        if suffix == ".html":
            parser = _HTMLReferences()
            parser.feed(text)
            parser.close()
            if not {"html", "head", "body", "title"}.issubset(parser.tags):
                raise ValidationError(f"Incomplete HTML document: {relative}")
            references.extend((relative, url) for url in parser.references)
            for css in parser.css:
                references.extend((relative, url) for url in _css_urls(css))
        elif suffix == ".css":
            references.extend((relative, url) for url in _css_urls(text))
        elif suffix in {".svg", ".xml"}:
            if re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", text, re.I):
                raise ValidationError(f"DTD/entity declarations are forbidden: {relative}")
            try:
                tree = ET.fromstring(text)
            except ET.ParseError as error:
                raise ValidationError(f"Invalid XML: {relative}: {error}") from error
            expected = f"{{{SVG_NAMESPACE}}}svg" if suffix == ".svg" else f"{{{SITEMAP_NAMESPACE}}}urlset"
            if tree.tag != expected:
                raise ValidationError(f"Unexpected XML root/namespace: {relative}")
            for element in tree.iter():
                for key, value in element.attrib.items():
                    if key.split("}")[-1] in {"href", "src"}:
                        references.append((relative, value))
                    else:
                        references.extend((relative, url) for url in _css_urls(value))
                if element.tag == f"{{{SITEMAP_NAMESPACE}}}loc" and element.text:
                    references.append((relative, element.text))
                elif element.tag == f"{{{SVG_NAMESPACE}}}style" and element.text:
                    references.extend((relative, url) for url in _css_urls(element.text))

    broken = []
    for source, url in references:
        target = _local_target(source, url)
        if target is not None and target not in contents:
            broken.append(f"{source}: {url!r} resolves to missing/non-allowlisted {target!r}")
    if broken:
        raise ValidationError("Broken local references:\n" + "\n".join(sorted(set(broken))))

    for endpoint in sorted(SERVER_ROUTES):
        if not re.search(r"(['\"])" + re.escape(endpoint) + r"\1", texts["app.js"]):
            raise ValidationError(f"app.js must preserve the existing endpoint {endpoint}")

    node = shutil.which("node")
    if not node:
        raise ValidationError("Node.js is required for JavaScript syntax checks (node --check)")
    for relative in ALLOWED:
        if not relative.endswith(".js"):
            continue
        # Check precisely the bytes being hashed, with no script execution or
        # package resolution; ignore NODE_OPTIONS so the host cannot inject code.
        environment = dict(os.environ)
        environment.pop("NODE_OPTIONS", None)
        environment.pop("NODE_PATH", None)
        try:
            result = subprocess.run(
                [node, "--check", "-"], input=contents[relative], capture_output=True,
                env=environment, timeout=15, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ValidationError(f"JavaScript syntax check could not finish: {relative}") from error
        if result.returncode:
            detail = result.stderr.decode("utf-8", errors="replace").strip()
            raise ValidationError(f"JavaScript syntax check failed: {relative}\n{detail}")
    return {relative: hashlib.sha256(contents[relative]).hexdigest() for relative in ALLOWED}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path,
                        default=Path(__file__).resolve().parents[1] / "public_html")
    parser.add_argument("--json", action="store_true", help="Print the SHA-256 manifest as JSON")
    args = parser.parse_args()
    try:
        manifest = validate(args.root)
    except (ValidationError, OSError, UnicodeError) as error:
        print(f"Frontend validation failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(manifest, indent=2) if args.json else f"Validated {len(manifest)} frontend files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
