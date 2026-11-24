import json
import tempfile
import unittest
from pathlib import Path

from sync import collect, sha256, sync


class ProviderSyncTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.release = self.root / "distribution"
        self.release.mkdir()
        self.local = {kind: self.root / "local" / kind for kind in ("import", "market")}
        self.remote = {kind: self.root / "remote" / kind for kind in self.local}
        for sources in (self.local, self.remote):
            self.write(sources["import"], "providers/sample/template.json", '{"version":"5","template":{"template_id":"sample","name":"Sample","supported_markets":["CN"]}}')
            self.write(sources["market"], "providers/sample/config.yaml", self.quote("1"))
            self.write(sources["market"], "LICENSE", "Example license\n")

    def write(self, root, relative, value):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")
        return path

    def quote(self, version):
        return f'id: sample-quote\nname: Example\nversion: "{version}"\nsupported_markets: [CN]\napi:\n  realtime: {{endpoint: /price}}\n'

    def test_local_handoff_retains_draft_until_upstream_matches(self):
        path = "providers/sample/config.yaml"
        self.write(self.local["market"], path, self.quote("2"))
        self.assertTrue(sync(self.release, self.local, False))
        current = self.release / "v1" / "market-sample-quote.yaml"
        expected = current.read_bytes()
        self.assertFalse(sync(self.release, self.remote, True))
        self.assertEqual(current.read_bytes(), expected)
        self.write(self.remote["market"], path, self.quote("2"))
        self.assertTrue(sync(self.release, self.remote, True))
        self.assertFalse((self.release / "upstream-pending.json").exists())
        self.write(self.remote["market"], path, self.quote("3"))
        self.assertTrue(sync(self.release, self.remote, True))
        self.assertNotEqual(current.read_bytes(), expected)

    def test_capabilities_hashes_and_excluded_fixtures(self):
        self.write(self.local["market"], "providers/mixed/config.yaml", self.quote("1").replace("sample-quote", "mixed") + "symbol_directory: {market: US_STOCK}\n")
        self.write(self.local["market"], "providers/directory/config.yaml", 'id: directory\nname: Directory\nversion: "1"\nsupported_markets: [HK]\nsymbol_directory: {market: HK_STOCK}\n')
        self.write(self.local["market"], "candidates/ignored/config.yaml", "ignored")
        self.write(self.local["import"], "providers/sample/fixtures/private.csv", "ignored")
        files, _, count = collect(self.local)
        self.assertEqual(count, 4)
        items = {item["id"]: item for item in json.loads(files["manifest.json"])["items"]}
        self.assertEqual(items["mixed"]["capabilities"], ["market_data", "stock_directory"])
        self.assertEqual(items["mixed"]["markets"], ["CN", "US"])
        self.assertEqual(items["directory"]["capabilities"], ["stock_directory"])
        for item in items.values():
            self.assertEqual(item["sha256"], sha256(files[item["file"]]))

    def test_rejects_embedded_credentials_and_duplicate_ids(self):
        path = "providers/bad/config.yaml"
        quote = self.quote("1").replace("sample-quote", "bad")
        self.write(self.local["market"], path, quote + "  headers: {Authorization: secret}\n")
        with self.assertRaisesRegex(ValueError, "invalid or unsafe"):
            collect(self.local)
        self.write(self.local["market"], path, quote + "  headers: {Authorization: 'Bearer ${TOKEN}'}\n")
        self.assertEqual(collect(self.local)[2], 3)
        self.write(self.local["market"], path, self.quote("1"))
        with self.assertRaisesRegex(ValueError, "duplicate provider ID"):
            collect(self.local)
