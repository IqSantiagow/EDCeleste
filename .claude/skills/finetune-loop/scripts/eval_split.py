"""Score a model on the test split of a dataset in the System One format and report the
same metrics for every model.

Ask a model (saves every raw answer to <results_dir>/eval_<name>.json):
    python eval_split.py ask --name jev --data_dir data/v3 --results_dir results \\
        --systemone https://openrouter.ai/api/v1/systemone \\
        --model typesafe/jev-1.13 --api_key_file secrets/openrouter_key
    python eval_split.py ask --name local-v3 --data_dir data/v3 \\
        --results_dir results --decider runs/v3/model
    python eval_split.py ask --name ollaya-winnow --data_dir data/v3 \\
        --results_dir results \\
        --systemone http://127.0.0.1:11435/v1/systemone --model winnow:e4b

Report (no model calls, works on saved answers):
    python eval_split.py report --data_dir data/v3 --results_dir results \\
        jev local-v3 [--extra my_metrics.py]

Metrics, per example "kind": question accuracy at 0.5, false "yes" and missed "yes"
counts at 0.5 / 0.7 / 0.9 (for noul questions), and the share of examples with every
question right.
--extra points to a python file with `extra_metrics(rows) -> dict[str, str]`,
rows = [(example, answers)], for project-specific metrics (e.g. "key pressed while
the pilot was only talking").
"""

import argparse
import importlib.util
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

THRESHOLDS = (0.5, 0.7, 0.9)


def load_examples(data_dir: Path, split: str | None = "test") -> list[dict]:
    examples = []
    for data_file in sorted(data_dir.glob("*.jsonl")):
        for line in data_file.read_text(encoding="utf-8").splitlines():
            example = json.loads(line)
            if split is None or example["split"] == split:
                examples.append(example)
    return examples


def systemone_asker(url: str, model: str, api_key: str | None):
    import httpx

    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    client = httpx.Client(headers=headers, timeout=120)

    def ask(state, questions: dict) -> dict:
        for attempt in range(4):
            response = client.post(
                url, json={"model": model, "state": state, "questions": questions}
            )
            if response.status_code in (429, 500, 502, 503) and attempt < 3:
                time.sleep(2 * (attempt + 1))
                continue
            response.raise_for_status()
            return response.json()["answers"]

    return ask


def decider_asker(model_path: str):
    from decider.infer import Decider

    decider = Decider(model_path)
    if sys.platform == "win32":
        # torch.compile needs Triton's compiler, skip it on Windows
        decider.eng._fwd_impl = decider.eng._fwd_eager

    def ask(state, questions: dict) -> dict:
        return decider.system_one(state, questions)["answers"]

    return ask


def is_right(answer: dict, gold, threshold: float = 0.5) -> bool:
    if "noul" in answer:
        return (answer["noul"] >= threshold) == bool(gold)
    return answer.get("choice") == gold


def command_ask(args) -> None:
    examples = load_examples(Path(args.data_dir))
    if args.decider:
        ask, workers = decider_asker(args.decider), 1
    else:
        api_key = os.environ.get(args.api_key_env, "") if args.api_key_env else ""
        if args.api_key_file:
            api_key = Path(args.api_key_file).read_text(encoding="utf-8").strip()
        ask, workers = (
            systemone_asker(args.systemone, args.model, api_key or None),
            args.workers,
        )
    print(f"{args.name}: {len(examples)} test examples")
    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        answered = list(
            pool.map(
                lambda example: {
                    "id": example["id"],
                    "answers": ask(example["state"], example["questions"]),
                },
                examples,
            )
        )
    seconds = time.perf_counter() - start
    results_dir = Path(args.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / f"eval_{args.name}.json").write_text(
        json.dumps(
            {
                "model": args.name,
                "data_dir": str(args.data_dir),
                "seconds": seconds,
                "answered": answered,
            }
        ),
        encoding="utf-8",
    )
    print(f"done in {seconds / 60:.1f} min -> {results_dir / f'eval_{args.name}.json'}")


def summarize(name: str, examples_by_id: dict, results_dir: Path, extra_module) -> dict:
    saved = json.loads((results_dir / f"eval_{name}.json").read_text(encoding="utf-8"))
    rows_by_kind: dict[str, list] = {}
    for answered in saved["answered"]:
        example = examples_by_id[answered["id"]]
        rows_by_kind.setdefault(example["kind"], []).append(
            (example, answered["answers"])
        )

    summary = {"model": name, "seconds": saved["seconds"], "kinds": {}}
    for kind, rows in sorted(rows_by_kind.items()):
        questions_right = questions_total = examples_all_right = 0
        false_yes = {threshold: 0 for threshold in THRESHOLDS}
        missed_yes = {threshold: 0 for threshold in THRESHOLDS}
        gold_no = gold_yes = 0
        for example, answers in rows:
            all_right = True
            for question_id, gold in example["gold"].items():
                answer = answers[question_id]
                if not isinstance(
                    answer, dict
                ):  # older result files kept only the yes-probability
                    answer = {"noul": answer}
                right = is_right(answer, gold)
                questions_right += right
                questions_total += 1
                all_right = all_right and right
                if "noul" in answer:
                    gold_yes += bool(gold)
                    gold_no += not gold
                    for threshold in THRESHOLDS:
                        false_yes[threshold] += (not gold) and answer[
                            "noul"
                        ] >= threshold
                        missed_yes[threshold] += (
                            bool(gold) and answer["noul"] < threshold
                        )
            examples_all_right += all_right
        summary["kinds"][kind] = {
            "examples": len(rows),
            "question_accuracy": questions_right / questions_total,
            "example_all_right": examples_all_right / len(rows),
            "false_yes": {
                str(threshold): [count, gold_no]
                for threshold, count in false_yes.items()
            },
            "missed_yes": {
                str(threshold): [count, gold_yes]
                for threshold, count in missed_yes.items()
            },
        }
    if extra_module:
        all_rows = [row for rows in rows_by_kind.values() for row in rows]
        summary["extra"] = extra_module.extra_metrics(all_rows)
    return summary


def print_summary(summary: dict) -> None:
    print(f"\n=== {summary['model']}  ({summary['seconds'] / 60:.1f} min)")
    for kind, metrics in summary["kinds"].items():
        false_yes = ", ".join(
            f"{threshold}: {count}/{total}"
            for threshold, (count, total) in metrics["false_yes"].items()
        )
        missed_yes = ", ".join(
            f"{threshold}: {count}/{total}"
            for threshold, (count, total) in metrics["missed_yes"].items()
        )
        questions_right = metrics["question_accuracy"]
        all_right = metrics["example_all_right"]
        print(
            f"  {kind:14} n={metrics['examples']:<5} questions {questions_right:.1%}  "
            f"all right {all_right:.1%}  "
            f"false yes [{false_yes}]  missed yes [{missed_yes}]"
        )
    for metric_name, value in summary.get("extra", {}).items():
        print(f"  {metric_name}: {value}")


def command_report(args) -> None:
    data_dir = Path(args.data_dir)
    examples_by_id = {
        example["id"]: example for example in load_examples(data_dir, split=None)
    }
    extra_module = None
    if args.extra:
        spec = importlib.util.spec_from_file_location("extra_metrics", args.extra)
        extra_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(extra_module)
    summaries = [
        summarize(name, examples_by_id, Path(args.results_dir), extra_module)
        for name in args.names
    ]
    for summary in summaries:
        print_summary(summary)
    (Path(args.results_dir) / "eval_summary.json").write_text(
        json.dumps(summaries, indent=2), encoding="utf-8"
    )


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)

    ask_parser = commands.add_parser("ask")
    ask_parser.add_argument("--name", required=True)
    ask_parser.add_argument("--data_dir", required=True)
    ask_parser.add_argument("--results_dir", required=True)
    ask_parser.add_argument(
        "--decider", help="local decider folder or HF id, scored in this process"
    )
    ask_parser.add_argument("--systemone", help="URL of a /v1/systemone endpoint")
    ask_parser.add_argument("--model", default="")
    ask_parser.add_argument("--api_key_file")
    ask_parser.add_argument("--api_key_env")
    ask_parser.add_argument("--workers", type=int, default=6)

    report_parser = commands.add_parser("report")
    report_parser.add_argument("--data_dir", required=True)
    report_parser.add_argument("--results_dir", required=True)
    report_parser.add_argument("--extra")
    report_parser.add_argument("names", nargs="+")

    args = parser.parse_args()
    if args.command == "ask":
        command_ask(args)
    else:
        command_report(args)


if __name__ == "__main__":
    main()
