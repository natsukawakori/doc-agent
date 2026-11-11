import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from eval.holdout.prepare_controlled_review import prepare


class ControlledReviewTest(unittest.TestCase):
    def test_review_preserves_actual_answer_and_attempts(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            case={'id':'N01','question':'问题','documents':[{'id':'a'*32,'text':'资料'}]}
            raw=(json.dumps(case,ensure_ascii=False)+'\n').encode()
            source=root/'cases.jsonl'; source.write_bytes(raw)
            manifest=root/'manifest.json'; manifest.write_text(json.dumps({'controlled_sha256':hashlib.sha256(raw).hexdigest()}),encoding='utf-8')
            records=[{'id':'N01','status':'error'}, {'id':'N01','status':'completed','question':'问题','documents':case['documents'],'answer':'资料不足'}]
            results=root/'results.jsonl'; results.write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in records),encoding='utf-8')
            target=root/'review'
            self.assertEqual(prepare(source,manifest,results,target),1)
            body=(target/'01_N01.md').read_text(encoding='utf-8')
            self.assertIn('资料不足',body); self.assertIn('运行尝试数：2；失败次数：1',body)
            self.assertIn('判断：正确 / 错误 / 无法判断',body)
            with self.assertRaises(FileExistsError): prepare(source,manifest,results,target)
            records[-1]['answer']='改'; records[-1]['documents']=[{'id':'b'*32,'text':'不一致'}]
            results.write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in records),encoding='utf-8')
            with self.assertRaises(ValueError): prepare(source,manifest,results,root/'review2')


if __name__=='__main__': unittest.main()
