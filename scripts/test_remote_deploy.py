import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch
import remote_deploy as remote


class DeployTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.root = self.base / 'public_html'
        self.backup = self.base / 'private-deploy'
        self.root.mkdir()
        self.backup.mkdir(mode=0o700)
        for name in remote.ALLOWED:
            target = self.root / name
            target.parent.mkdir(exist_ok=True)
            target.write_bytes(b'before ' + name.encode())
        for name in ('api.php', '.htaccess', 'default.php'):
            (self.root / name).write_bytes(b'must not change')
        self.customer_files = {
            'customerdata/leads/2026/example.json': b'private lead fixture',
            'customerdata/.htaccess': b'deny all fixture',
            'customerdata/uploads/quote.bin': b'private upload fixture',
        }
        for name, content in self.customer_files.items():
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        self.data = {name: b'after ' + name.encode() for name in remote.ALLOWED}
        self.release = 'a' * 40 + '-1-1'

    def tearDown(self):
        self.temp.cleanup()

    def payload(self, extra=None):
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w') as archive:
            archive.writestr('manifest.json', json.dumps({name: hashlib.sha256(content).hexdigest() for name, content in self.data.items()}))
            for name, content in self.data.items():
                archive.writestr(name, content)
            if extra:
                archive.writestr(extra, b'forbidden')
        return output.getvalue()

    def deploy(self, checker=lambda *_: None):
        return remote.transact(str(self.root), str(self.backup), self.release, self.payload(), checker)

    def assert_frontend_restored(self):
        for name in remote.ALLOWED:
            self.assertEqual((self.root / name).read_bytes(), b'before ' + name.encode())

    def assert_customerdata_preserved(self):
        actual = {str(path.relative_to(self.root)): path.read_bytes()
                  for path in (self.root / 'customerdata').rglob('*') if path.is_file()}
        self.assertEqual(actual, self.customer_files)

    def test_success_preserves_backend_and_backup(self):
        self.deploy()
        for name, content in self.data.items():
            self.assertEqual((self.root / name).read_bytes(), content)
            self.assertEqual((self.backup / self.release / 'before' / name).read_bytes(), b'before ' + name.encode())
        for name in ('api.php', '.htaccess', 'default.php'):
            self.assertEqual((self.root / name).read_bytes(), b'must not change')
        self.assert_customerdata_preserved()

    def test_failed_smoke_rolls_back_all_frontend(self):
        def fail(*_):
            raise RuntimeError('test HTTP failure')
        with patch.object(remote.time, 'sleep'), self.assertRaises(RuntimeError):
            self.deploy(fail)
        self.assert_frontend_restored()
        self.assert_customerdata_preserved()

    def test_status_write_failure_cannot_prevent_rollback(self):
        original_write = Path.write_text
        status_writes = 0

        def fail_after_backup(path, content, *args, **kwargs):
            nonlocal status_writes
            if path.name == 'status.json':
                status_writes += 1
                if status_writes >= 2:
                    raise OSError('simulated status write failure')
            return original_write(path, content, *args, **kwargs)

        with patch.object(Path, 'write_text', fail_after_backup):
            with self.assertRaisesRegex(OSError, 'simulated status write failure'):
                self.deploy()
        self.assertGreaterEqual(status_writes, 3)
        self.assert_frontend_restored()
        self.assert_customerdata_preserved()
        for name in remote.ALLOWED:
            self.assertEqual((self.backup / self.release / 'before' / name).read_bytes(),
                             b'before ' + name.encode())

    def test_incomplete_prior_release_blocks_before_new_transfer(self):
        prior = self.backup / ('b' * 40 + '-2-1')
        prior.mkdir(mode=0o700)
        for state in (None, 'backed-up', 'rollback-started'):
            with self.subTest(state=state):
                if state is not None:
                    (prior / 'status.json').write_text(json.dumps({'state': state}))
                with self.assertRaisesRegex(RuntimeError, 'Prior deployment is incomplete'):
                    self.deploy()
                self.assertFalse((self.backup / self.release).exists())
                self.assert_frontend_restored()
                self.assert_customerdata_preserved()

    def test_mid_transfer_failure_restores_entire_frontend(self):
        original_replace = remote.replace_file
        calls = 0

        def fail_once(source, target, mode):
            nonlocal calls
            calls += 1
            if calls == 4:
                raise OSError('simulated fourth replacement failure')
            return original_replace(source, target, mode)

        with patch.object(remote, 'replace_file', fail_once):
            with self.assertRaisesRegex(OSError, 'simulated fourth replacement failure'):
                self.deploy()
        self.assertEqual(calls, 4 + len(remote.ALLOWED))
        self.assert_frontend_restored()
        self.assert_customerdata_preserved()
        record = json.loads((self.backup / self.release / 'status.json').read_text())
        self.assertEqual(record['state'], 'rolled-back')

    def test_termination_during_smoke_is_not_retried(self):
        checks = 0

        def interrupted(*_):
            nonlocal checks
            checks += 1
            raise SystemExit('simulated termination signal')

        with patch.object(remote.time, 'sleep') as sleep:
            with self.assertRaisesRegex(SystemExit, 'simulated termination signal'):
                self.deploy(interrupted)
        self.assertEqual(checks, 1)
        sleep.assert_not_called()
        self.assert_frontend_restored()
        self.assert_customerdata_preserved()

    def test_nested_customerdata_metadata_is_untouched(self):
        before = {name: (self.root / name).stat() for name in self.customer_files}
        self.deploy()
        self.assert_customerdata_preserved()
        for name, info in before.items():
            after = (self.root / name).stat()
            self.assertEqual((after.st_ino, after.st_mtime_ns, after.st_mode),
                             (info.st_ino, info.st_mtime_ns, info.st_mode))

    def test_reject_extra_backend_or_traversal(self):
        for path in ('api.php', '../escape', '.htaccess'):
            with self.assertRaises(ValueError):
                remote.unpack(self.payload(path))

    def test_reject_symlink(self):
        target = self.root / 'app.js'
        target.unlink()
        target.symlink_to(self.root / 'analytics.js')
        with self.assertRaises(ValueError):
            self.deploy()

    def test_reject_backup_inside_webroot(self):
        bad = self.root / 'backups'
        bad.mkdir(mode=0o700)
        with self.assertRaises(ValueError):
            remote.transact(str(self.root), str(bad), self.release, self.payload())

    def test_allowlists_match(self):
        from validate_frontend import ALLOWED
        self.assertEqual(set(ALLOWED), set(remote.ALLOWED))

    def test_assets_before_html(self):
        self.assertTrue(all(not name.endswith('.html') for name in remote.ORDER[:-2]))

    def test_reject_missing_existing_file(self):
        (self.root / 'app.js').unlink()
        with self.assertRaises(ValueError):
            self.deploy()
        self.assertEqual((self.root / 'styles.css').read_bytes(), b'before styles.css')


if __name__ == '__main__':
    unittest.main()
