import unittest
from eval.reconcile_annotations import reconcile


class ReconcileTest(unittest.TestCase):
    def test_unknown_and_id_alignment(self):
        annotation = '\n'.join(f'## {i}. 题目 {i} 标题\n### 人工判断：**正确**\n1. **主张**：测试\n标签：**支持**\n待核：一部分\n' for i in range(20))
        rows = [{'id': str(i), 'question': '问题', 'answer': '答'} for i in range(20)]
        cases, claims, _ = reconcile(annotation, rows, [])
        self.assertEqual(len(cases), 20)
        self.assertTrue(all(row['label'] == 'unknown' for row in claims))
        with self.assertRaises(ValueError):
            reconcile(annotation, rows[:-1], [])
