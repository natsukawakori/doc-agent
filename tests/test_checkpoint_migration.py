import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from eval import migrate_memory_checkpoint as migration


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class CheckpointMigrationTest(unittest.TestCase):
    def test_preserves_original_rankings_and_rejects_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            code = root/'eval'
            data = root/'data'/'dureader'
            cache = data/'bge_full_cache'
            code.mkdir(parents=True)
            cache.mkdir(parents=True)
            for name in ('stream_rank.py', 'vector_cache.py', 'full_stream.py', 'full_guard.py', 'process_memory.py'):
                (code/name).write_text(name, encoding='utf-8')
            queries = data/'full_queries.json'
            queries.write_text('{}', encoding='utf-8')
            with (cache/'vectors.f32').open('wb') as f:
                f.truncate(4096*512*4)
            with (cache/'ids.bin').open('wb') as f:
                f.truncate(4096*32)
            signature = {'engine_sha256':'old-engine','guard_code_sha256':'old-guard',
                         'ranker_sha256':digest(code/'stream_rank.py'),
                         'cache_code_sha256':digest(code/'vector_cache.py'),
                         'queries_sha256':digest(queries),'cache_dir':str(cache)}
            original = {'signature':signature, 'processed':4096, 'rankings':[[[.5,-1,'a'*32]]] + [[] for _ in range(99)],
                        'found_gold_ids':['a'*32], 'active_seconds':10.0}
            old, new = data/'old.json', data/'new.json'
            old.write_text(json.dumps(original), encoding='utf-8')
            before = old.read_bytes()
            args = ['migration', str(old), str(new)]
            with patch.object(migration, 'ROOT', root), patch.object(migration, 'OLD_ENGINE', 'old-engine'), patch.object(migration, 'OLD_GUARD', 'old-guard'), patch.object(sys, 'argv', args), patch('builtins.print'):
                migration.main()
                with self.assertRaises(FileExistsError):
                    migration.main()
            updated = json.loads(new.read_text(encoding='utf-8'))
            self.assertEqual(updated['rankings'], original['rankings'])
            self.assertEqual(updated['processed'], 4096)
            self.assertEqual(updated['found_gold_ids'], original['found_gold_ids'])
            self.assertEqual(old.read_bytes(), before)
            self.assertEqual(updated['signature']['memory_code_sha256'], digest(code/'process_memory.py'))


if __name__ == '__main__':
    unittest.main()
