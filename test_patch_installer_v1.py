"""Self-contained installer regression tests (also runnable before full repo)."""
import unittest
from apply_cpu_stability_v1 import transform, SERVER_OLD, APP_OLD, MARK


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.server = (
            "from functools import lru_cache\n" + SERVER_OLD +
            "        return 'cached'\n    except Exception:\n        return None\n"
        )
        self.app = (
            "async function runCpuTurn(){\n" + APP_OLD +
            "\n// more UI code\n"
        )

    def test_changes_both_files(self):
        server, app, changed = transform(self.server, self.app)
        self.assertTrue(changed)
        self.assertIn('def _mathml_cached(expression):', server)
        self.assertIn('recoverCpuAfterError(e)', app)
        self.assertEqual(server.count(MARK), 1)
        self.assertEqual(app.count(MARK), 1)

    def test_second_application_is_noop(self):
        server, app, _ = transform(self.server, self.app)
        again_server, again_app, changed = transform(server, app)
        self.assertFalse(changed)
        self.assertEqual((server, app), (again_server, again_app))

    def test_missing_anchor_aborts(self):
        with self.assertRaises(RuntimeError):
            transform(self.server.replace(SERVER_OLD, 'changed'), self.app)
        with self.assertRaises(RuntimeError):
            transform(self.server, self.app.replace(APP_OLD, 'changed'))

    def test_partial_install_aborts(self):
        server, app, _ = transform(self.server, self.app)
        with self.assertRaises(RuntimeError):
            transform(server, self.app)
        with self.assertRaises(RuntimeError):
            transform(self.server, app)

    def test_no_duplicate_anchor_tolerated(self):
        with self.assertRaises(RuntimeError):
            transform(self.server + SERVER_OLD, self.app)


if __name__ == '__main__':
    unittest.main(verbosity=2)
