import unittest
from eval.prepare_holdout30 import choose
from eval.holdout.sample import SEED, controlled_cases, questions_from


class FinalSamplingTest(unittest.TestCase):
    def test_reproducible_and_excludes_known_ids_texts_and_positives(self):
        prior=[{'id':'old','text':'已 用问题','positive_ids':['used']}]
        rows=[{'query_id':'old','query':'另一问题','positive_passages':[{'docid':'a'}],'negative_passages':[{}]},
              {'query_id':'2','query':'已用问题','positive_passages':[{'docid':'b'}],'negative_passages':[{}]},
              {'query_id':'3','query':'第三题','positive_passages':[{'docid':'used'}],'negative_passages':[{}]},
              {'query_id':'4','query':'第四题','positive_passages':[{'docid':'good1'}],'negative_passages':[{}]},
              {'query_id':'5','query':'第五题','positive_passages':[{'docid':'good2'}],'negative_passages':[{}]}]
        result,n=choose(rows,prior,count=2,seed=SEED)
        self.assertEqual({x['id'] for x in result},{'4','5'})
        self.assertEqual((result,n),choose(list(reversed(rows)),prior,count=2,seed=SEED))

    def test_controlled_scenarios_have_distinct_documents_and_questions(self):
        rows=controlled_cases()
        self.assertEqual(len(rows),10)
        self.assertEqual(len({x['question'] for x in rows}),10)
        self.assertEqual(len({x['documents'][0]['id'] for x in rows}),10)
        self.assertTrue(all(x['scope']=='controlled' for x in rows))
        self.assertEqual(list(questions_from({'x':[{'question':'问题'}]})),['问题'])


if __name__=='__main__': unittest.main()
