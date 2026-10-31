"""웹 자동 저장 파일을 매 호출마다 최신으로 읽는 LiveSnapshot과 파일 안 source 정보 (#65)."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from handoff import HandoffError, LiveSnapshot, Snapshot

REV_A = "a" * 40
REV_B = "b" * 40


def web_file(fingerprint="demo-sql-001", revision=REV_A, repository="demo/example", prompt="쿼리를 매개변수로 바꾸세요."):
    """웹(frontend/src/lib/mcp.ts)이 저장하는 형식: API 응답 형식 + source"""
    return {
        "mode": "red_blue",
        "source": {"repository": repository, "revision": revision, "generated_at": "2026-10-31T05:00:00Z"},
        "results": [{
            "fingerprint": fingerprint, "status": "done",
            "explanation": {
                "fingerprint": fingerprint, "variant": "D", "red_verdict": "pass",
                "red_rounds": [{"verdict": "pass", "issues": []}],
                "needs_manual_review": False, "false_positive_suspect": False,
                "ai_fix_prompt": prompt, "model": "fixture", "prompt_version": "test-1",
            },
        }],
    }


class LiveSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "72hours-mcp-demo-example.json"
        self.tick = 1_700_000_000

    def write(self, data):
        text = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
        self.path.write_text(text, encoding="utf-8")
        # 같은 초 안의 두 번 저장도 구분되게 수정 시각을 직접 올립니다
        self.tick += 10
        os.utime(self.path, (self.tick, self.tick))

    def test_reads_latest_file_without_restart(self):
        self.write(web_file("old-finding", REV_A))
        live = LiveSnapshot(self.path, "demo/example")
        first = live.list_findings()
        self.assertEqual([f["fingerprint"] for f in first["findings"]], ["old-finding"])
        self.assertEqual(first["source"]["revision"], REV_A)
        self.assertEqual(first["source"]["binding"], "file_supplied_not_verified_by_mcp")
        self.assertEqual(first["source"]["generated_at"], "2026-10-31T05:00:00Z")

        # 재검사: 같은 파일에 새 커밋·새 결과를 덮어씀 → 재시작 없이 반영
        self.write(web_file("new-finding", REV_B, prompt="새 지시"))
        second = live.list_findings()
        self.assertEqual([f["fingerprint"] for f in second["findings"]], ["new-finding"])
        self.assertEqual(second["source"]["revision"], REV_B)
        self.assertIn("새 지시", live.fix_prompt("new-finding"))
        with self.assertRaises(HandoffError):
            live.fix_prompt("old-finding")

    def test_does_not_reread_unchanged_file(self):
        self.write(web_file())
        live = LiveSnapshot(self.path)
        live.list_findings()
        loaded = live._snapshot
        live.list_findings()
        live.fix_prompt("demo-sql-001")
        self.assertIs(live._snapshot, loaded)

    def test_keeps_last_good_result_when_new_file_is_broken(self):
        self.write(web_file())
        live = LiveSnapshot(self.path, "demo/example")
        self.assertTrue(live.list_findings()["findings"][0]["ready"])
        self.write('{"mode": "red_blue", "results": [')  # 저장 도중이거나 깨진 파일
        listing = live.list_findings()
        self.assertEqual(listing["findings"][0]["fingerprint"], "demo-sql-001")
        self.assertIn("직전 결과", listing["notice"])
        self.assertIn("쿼리", live.fix_prompt("demo-sql-001"))
        # 다시 정상 파일이 오면 안내가 사라짐
        self.write(web_file("fixed"))
        listing = live.list_findings()
        self.assertNotIn("notice", listing)
        self.assertEqual(listing["findings"][0]["fingerprint"], "fixed")

    def test_pinned_repository_rejects_other_repository_file(self):
        self.write(web_file(repository="demo/example"))
        live = LiveSnapshot(self.path, "demo/example")
        live.list_findings()
        self.write(web_file("other-repo-finding", repository="attacker/other"))
        listing = live.list_findings()
        self.assertEqual(listing["findings"][0]["fingerprint"], "demo-sql-001")
        self.assertIn("저장소", listing["notice"])
        with self.assertRaises(HandoffError):
            live.fix_prompt("other-repo-finding")
        # 처음부터 다른 저장소면 아무것도 전달하지 않음
        fresh = LiveSnapshot(self.path, "demo/example")
        self.assertEqual(fresh.list_findings()["findings"], [])
        with self.assertRaises(HandoffError):
            fresh.fix_prompt("other-repo-finding")

    def test_missing_file_explains_next_step(self):
        live = LiveSnapshot(self.path, "demo/example")
        listing = live.list_findings()
        self.assertEqual(listing["findings"], [])
        self.assertIn("자동 저장", listing["notice"])
        with self.assertRaises(HandoffError):
            live.fix_prompt("demo-sql-001")
        self.write(web_file())  # 나중에 웹이 저장하면 바로 읽힘
        self.assertEqual(len(live.list_findings()["findings"]), 1)

    def test_live_mode_requires_revision_in_file(self):
        data = web_file()
        del data["source"]["revision"]
        self.write(data)
        listing = LiveSnapshot(self.path, "demo/example").list_findings()
        self.assertEqual(listing["findings"], [])
        self.assertIn("커밋", listing["notice"])

    def test_invalid_arguments(self):
        with self.assertRaises(HandoffError):
            LiveSnapshot(Path("relative.json"))
        with self.assertRaises(HandoffError):
            LiveSnapshot(self.path, "not-a-repo")


class FileSourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "r.json"

    def test_fixed_mode_rejects_file_from_other_commit(self):
        self.path.write_text(json.dumps(web_file(revision=REV_B)), encoding="utf-8")
        with self.assertRaises(HandoffError) as caught:
            Snapshot(self.path, "demo/example", REV_A)
        self.assertIn("--revision", str(caught.exception))
        # 같은 커밋이면 기존 방식 그대로 동작
        ok = Snapshot(self.path, "demo/example", REV_B)
        self.assertEqual(ok.list_findings()["source"]["binding"], "operator_supplied_not_verified_by_mcp")

    def test_malformed_source_is_rejected(self):
        for source in ({"repository": "../../etc"}, {"revision": "HEAD"}, "demo/example"):
            with self.subTest(source=source):
                data = web_file()
                data["source"] = source
                self.path.write_text(json.dumps(data), encoding="utf-8")
                with self.assertRaises(HandoffError):
                    Snapshot(self.path, None, None)

    def test_secret_like_generated_at_is_dropped(self):
        data = web_file()
        data["source"]["generated_at"] = "sk-" + "Z" * 24
        self.path.write_text(json.dumps(data), encoding="utf-8")
        listing = Snapshot(self.path, None, None).list_findings()
        self.assertIsNone(listing["source"]["generated_at"])


if __name__ == "__main__":
    unittest.main()
