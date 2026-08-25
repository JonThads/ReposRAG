"""
ReposRAG evaluation runner.

Runs the hand-written Q&A test set (qa_testset.json) against the live /query
API, then scores faithfulness and answer relevancy using DeepEval, with the
local Ollama model acting as the judge LLM (no paid API required).

Usage:
    python -m eval.run_eval --api-url http://localhost:8000
"""

import argparse
import csv
import json
import sys
from pathlib import Path

import httpx
from deepeval.metrics import AnswerRelevancyMetric, FaithfulnessMetric
from deepeval.models.base_model import DeepEvalBaseLLM
from deepeval.test_case import LLMTestCase

sys.path.append(str(Path(__file__).resolve().parent.parent))
from api.config import settings  # noqa: E402


class OllamaJudge(DeepEvalBaseLLM):
    """Wraps a local Ollama model so DeepEval can use it as the judge LLM."""

    def __init__(self, model_name: str = None, host: str = None):
        self.model_name = model_name or settings.ollama_model
        self.host = host or settings.ollama_host

    def load_model(self):
        return self.model_name

    def generate(self, prompt: str) -> str:
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(
                f"{self.host}/api/generate",
                json={"model": self.model_name, "prompt": prompt, "stream": False, "format": "json"},
            )
            resp.raise_for_status()
            return resp.json().get("response", "").strip()

    async def a_generate(self, prompt: str) -> str:
        return self.generate(prompt)

    def get_model_name(self) -> str:
        return f"ollama/{self.model_name}"


def load_testset(path: Path):
    with open(path) as f:
        return json.load(f)


def run_queries(api_url: str, testset):
    results = []
    with httpx.Client(timeout=120.0) as client:
        for item in testset:
            resp = client.post(
                f"{api_url}/query",
                json={"question": item["question"], "repo": item.get("repo")},
            )
            resp.raise_for_status()
            data = resp.json()
            results.append(
                {
                    "question": item["question"],
                    "expected_answer": item["expected_answer"],
                    "actual_answer": data["answer"],
                    "retrieval_context": [s["repo"] + "/" + s["file_path"] for s in data["sources"]],
                    "context_text": [
                        f"{s['repo']}/{s['file_path']}#{s['chunk_index']} (sim={s['similarity']:.3f})"
                        for s in data["sources"]
                    ],
                }
            )
    return results


def score_results(results, judge: OllamaJudge):
    faithfulness = FaithfulnessMetric(model=judge, threshold=0.5)
    relevancy = AnswerRelevancyMetric(model=judge, threshold=0.5)

    scored = []
    for r in results:
        test_case = LLMTestCase(
            input=r["question"],
            actual_output=r["actual_answer"],
            expected_output=r["expected_answer"],
            retrieval_context=r["context_text"],
        )
        faithfulness.measure(test_case)
        relevancy.measure(test_case)
        scored.append(
            {
                "question": r["question"],
                "ai_generated_answer": r["actual_answer"],
                "answer": r["expected_answer"],
                "faithfulness_score": round(faithfulness.score, 3),
                "answer_relevancy_score": round(relevancy.score, 3),
                "sources": "; ".join(r["retrieval_context"]),
            }
        )
    return scored


def write_report(scored, out_path: Path):
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "question",
                "ai_generated_answer",
                "answer",
                "faithfulness_score",
                "answer_relevancy_score",
                "sources",
            ],
        )
        writer.writeheader()
        writer.writerows(scored)
    print(f"Wrote eval report to {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Run ReposRAG evaluation.")
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument(
        "--testset", default=str(Path(__file__).parent / "qa_testset.json")
    )
    parser.add_argument(
        "--out", default=str(Path(__file__).parent / "eval_report.csv")
    )
    args = parser.parse_args()

    testset = load_testset(Path(args.testset))
    print(f"Loaded {len(testset)} test cases.")

    results = run_queries(args.api_url, testset)
    print("Collected answers from the live API. Scoring with DeepEval (Ollama judge)...")

    judge = OllamaJudge()
    scored = score_results(results, judge)

    for row in scored:
        print(
            f"- {row['question'][:60]:<60} "
            f"faithfulness={row['faithfulness_score']:.2f} "
            f"relevancy={row['answer_relevancy_score']:.2f}"
        )

    write_report(scored, Path(args.out))

    avg_faith = sum(r["faithfulness_score"] for r in scored) / len(scored)
    avg_rel = sum(r["answer_relevancy_score"] for r in scored) / len(scored)
    print(f"\nAverage faithfulness: {avg_faith:.3f}")
    print(f"Average answer relevancy: {avg_rel:.3f}")


if __name__ == "__main__":
    main()
