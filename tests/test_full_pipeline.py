import gzip
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import torch
from eval import full_stream
from eval.cache_search import search_vectors


class FakeModel:
    def __init__(self, *args, **kwargs):
        self.max_seq_length = None

    def encode(self, texts, **kwargs):
        return torch.tensor([[0., 1.] if text == 'other' else [1., 0.] for text in texts])


class FullPipelineTest(unittest.TestCase):
    def test_scan_checkpoint_cache_and_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            corpus = root/'corpus.gz'
            with gzip.open(corpus, 'wt', encoding='utf-8') as f:
                f.write('a'*32 + '\trelevant\n' + 'b'*32 + '\tother\n')
            corpus_hash = hashlib.sha256(corpus.read_bytes()).hexdigest()
            queries = root/'queries.json'
            queries.write_text(json.dumps({'queries': [{'id':str(i), 'text':'query', 'positive_ids':['a'*32]} for i in range(100)]}), encoding='utf-8')
            qhash = hashlib.sha256(queries.read_bytes()).hexdigest()
            manifest = root/'manifest.json'
            manifest.write_text(json.dumps({'queries_sha256':qhash, 'model_revision':full_stream.REVISION, 'corpus_sha256':corpus_hash}), encoding='utf-8')
            checkpoint, output, cache = root/'checkpoint.json', root/'result.json', root/'cache'
            args = ['full_stream', str(corpus), str(queries), str(manifest), str(checkpoint), str(output), '--device', 'cpu', '--cache-dir', str(cache)]
            with patch.object(sys, 'argv', args), patch.object(full_stream, 'CORPUS_SHA', corpus_hash), patch.object(full_stream, 'SentenceTransformer', FakeModel), patch('builtins.print'):
                full_stream.main()
            result=json.loads(output.read_text(encoding='utf-8'))
            self.assertEqual(result['summary']['hit1'], 1.0)
            self.assertEqual(result['metadata']['corpus_passages'], 2)
            self.assertEqual(json.loads(checkpoint.read_text(encoding='utf-8'))['processed'], 2)
            ranking=search_vectors(cache, torch.tensor([[1.,0.]]), 2, verify=True)
            self.assertEqual([x['id'] for x in ranking[0]], ['a'*32, 'b'*32])
            with patch.object(sys, 'argv', args), patch.object(full_stream, 'CORPUS_SHA', corpus_hash):
                with self.assertRaises(FileExistsError):
                    full_stream.main()


if __name__ == '__main__':
    unittest.main()
