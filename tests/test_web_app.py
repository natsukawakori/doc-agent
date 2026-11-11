import json
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

from fastapi.testclient import TestClient
from app.server import app
from app.state import sessions


class WebAppTest(unittest.TestCase):
    def test_streams_events_and_retains_session_history(self):
        received = []
        def fake_run(question, history, observer, on_delta, execution_control=None):
            received.append((question, list(history)))
            observer({"type": "model_start"})
            on_delta("回答")
            observer({"type": "assistant", "content": "回答", "tool_calls": []})
            return "回答"

        with tempfile.TemporaryDirectory() as tmp, patch("app.stream.PROJECT", Path(tmp)), \
             patch("app.stream.run", side_effect=fake_run), patch("app.stream.compress", side_effect=lambda h, observer=None: h):
            with TestClient(app) as client:
                session = client.post("/api/session").json()["session_id"]
                for question in ("第一题", "第二题"):
                    response = client.post("/chat", json={"session_id": session, "question": question})
                    self.assertEqual(response.status_code, 200)
                    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
                    self.assertEqual([e["type"] for e in events], ["user", "model_start", "delta", "assistant", "done"])
                    self.assertEqual(events[-1]["answer"], "回答")
                self.assertEqual(received[1][1], [{"role": "user", "content": "第一题"},
                                                  {"role": "assistant", "content": "回答"}])
                records = (Path(tmp) / "data/reports/web_sessions" / (session + ".jsonl")).read_text(encoding="utf8")
                self.assertIn("第一题", records)
                self.assertIn("第二题", records)
                self.assertEqual(client.post("/api/session", headers={"Origin": "https://example.com"}).status_code, 403)
        sessions.clear()

    @unittest.skipUnless(
        (Path(__file__).resolve().parent.parent / "data" / "dureader" / "full_queries.json").exists(),
        "需要本地 DuReader 题集，数据不随仓库分发",
    )
    def test_recommendations_come_from_fixed_dataset(self):
        with TestClient(app) as client:
            response = client.get("/api/recommendations")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.json()["questions"]), 4)

    def test_real_agent_stream_survives_gbk_stdout(self):
        delta = NS(content="✅ 公式 $x_i^2$", tool_calls=[], reasoning_content=None)
        chunk = NS(choices=[NS(delta=delta)])
        raw = io.BytesIO()
        stdout = io.TextIOWrapper(raw, encoding="gbk", errors="strict", write_through=True)
        with tempfile.TemporaryDirectory() as tmp, patch("app.stream.PROJECT", Path(tmp)), \
             patch("src.trace.DB", Path(tmp) / "trace.db"), \
             patch("src.agent.chat", return_value=iter([chunk])), redirect_stdout(stdout):
            with TestClient(app) as client:
                session = client.post("/api/session").json()["session_id"]
                response = client.post("/chat", json={"session_id": session, "question": "测试"})
                events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
                self.assertEqual(events[-1]["type"], "done")
                self.assertEqual(events[-1]["answer"], "✅ 公式 $x_i^2$")
                self.assertIn("✅ 公式 $x_i^2$", "".join(e.get("content", "") for e in events if e["type"] == "delta"))
        stdout.detach()
        sessions.clear()


if __name__ == "__main__":
    unittest.main()
