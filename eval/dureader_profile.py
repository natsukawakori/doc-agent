"""Measure actual local search stages without changing project code."""
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
total_start = time.perf_counter()
from src import rag
from eval.process_memory import memory
import torch
import sentence_transformers as st

timings = {}
original_retrieve = rag.retrieve_many
original_passages = rag.get_passages
original_cross = st.CrossEncoder


def retrieve(*args, **kwargs):
    start = time.perf_counter()
    result = original_retrieve(*args, **kwargs)
    timings["vector_retrieve_including_model_seconds"] = time.perf_counter() - start
    return result


def passages(*args, **kwargs):
    start = time.perf_counter()
    result = original_passages(*args, **kwargs)
    timings["passage_lookup_seconds"] = time.perf_counter() - start
    return result


class Cross:
    def __init__(self, *args, **kwargs):
        start = time.perf_counter()
        self.model = original_cross(*args, **kwargs)
        timings["reranker_load_seconds"] = time.perf_counter() - start

    def predict(self, *args, **kwargs):
        start = time.perf_counter()
        result = self.model.predict(*args, **kwargs)
        timings["reranker_predict_seconds"] = time.perf_counter() - start
        return result


query = "native app是什么"
start = time.perf_counter()
with patch.object(rag, "retrieve_many", retrieve), patch.object(rag, "get_passages", passages), patch.object(st, "CrossEncoder", Cross):
    results = rag.search(query)
timings["search_seconds"] = time.perf_counter() - start
timings["process_seconds_including_imports"] = time.perf_counter() - total_start
report = {"query": query, "timings": timings, "memory": memory(),
          "cuda_peak_mib": round(torch.cuda.max_memory_allocated() / 1024**2, 2),
          "source_ids": [r["source"] for r in results]}
folder = Path(__file__).resolve().parent.parent / "data" / "reports"
folder.mkdir(parents=True, exist_ok=True)
(folder / ("dureader_profile_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".json")).write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
print(json.dumps(report, ensure_ascii=False), flush=True)
