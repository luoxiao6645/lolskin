"""lcu 模块测试：lockfile 解析、过期判定、日志回退、RiotClient。"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ysnskin_learn.lcu import (
    LcuError,
    Lockfile,
    RiotClient,
    discover,
    find_lockfile,
    read_lockfile,
)


class TestLockfileParsing(unittest.TestCase):
    def test_parse_valid(self):
        lockfile = read_lockfile(Path("nonexistent"))
        self.assertIsNone(lockfile)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "lockfile"
            path.write_text("LeagueClient:1234:54321:sekret:https", encoding="utf-8")
            parsed = read_lockfile(path)
            self.assertEqual(parsed.process_name, "LeagueClient")
            self.assertEqual(parsed.pid, 1234)
            self.assertEqual(parsed.port, 54321)
            self.assertEqual(parsed.token, "sekret")

    def test_parse_garbage(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "lockfile"
            path.write_text("not-a-lockfile", encoding="utf-8")
            self.assertIsNone(read_lockfile(path))

    def test_find_lockfile_locations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "LeagueClient").mkdir()
            (root / "LeagueClient" / "lockfile").write_text(
                "LeagueClient:1:2:t:https", encoding="utf-8"
            )
            self.assertEqual(find_lockfile(root), root / "LeagueClient" / "lockfile")


class TestDiscover(unittest.TestCase):
    @mock.patch("ysnskin_learn.lcu._process_alive", return_value=True)
    def test_lockfile_priority(self, _alive):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "LeagueClient").mkdir()
            (root / "LeagueClient" / "lockfile").write_text(
                "LeagueClient:42:9999:tok:https", encoding="utf-8"
            )
            result = discover(root)
            self.assertEqual(result.port, 9999)
            self.assertEqual(result.token, "tok")

    @mock.patch("ysnskin_learn.lcu._process_alive", return_value=False)
    def test_stale_lockfile_falls_back_to_logs(self, _alive):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "LeagueClient").mkdir()
            (root / "LeagueClient" / "lockfile").write_text(
                "LeagueClient:42:9999:tok:https", encoding="utf-8"
            )
            (root / "LeagueClient" / "LeagueClientUx.log").write_text(
                "--app-port=7777 --remoting-auth-token=fromlog", encoding="utf-8"
            )
            result = discover(root)
            self.assertEqual(result.port, 7777)
            self.assertEqual(result.token, "fromlog")

    def test_no_credentials_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(LcuError):
                discover(Path(tmp))


class TestRiotClient(unittest.TestCase):
    def _make_client(self):
        return RiotClient(Lockfile("LeagueClient", 1, 54321, "tok", "https"))

    def test_auth_header(self):
        client = self._make_client()
        self.assertTrue(client._auth.startswith("Basic "))

    def test_request_builds_url_and_auth(self):
        client = self._make_client()
        with mock.patch("urllib.request.urlopen") as urlopen:
            resp = mock.MagicMock()
            resp.status = 200
            resp.read.return_value = b'{"phase":"ChampSelect"}'
            resp.__enter__ = lambda self: self
            resp.__exit__ = mock.MagicMock(return_value=False)
            urlopen.return_value = resp
            status, raw = client.request("GET", "/lol-gameflow/v1/gameflow-phase")
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(raw), {"phase": "ChampSelect"})
            req = urlopen.call_args[0][0]
            self.assertEqual(req.full_url, "https://127.0.0.1:54321/lol-gameflow/v1/gameflow-phase")
            self.assertEqual(req.get_method(), "GET")
            self.assertEqual(req.headers["Authorization"], client._auth)


if __name__ == "__main__":
    unittest.main()
