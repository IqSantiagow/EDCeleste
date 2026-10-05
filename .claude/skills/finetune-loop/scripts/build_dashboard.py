"""Build the progress dashboard (one self-contained HTML page) from the iteration
registry, ready to publish as an artifact.

    python build_dashboard.py <workspace>/iterations.json <workspace>/dashboard.html

iterations.json (paths relative to the file):
{
  "title": "My decision model",
  "lede": "One or two sentences: what the model decides and what 'good' means.",
  "data_dir": "training_data",            # the test split every entry was scored on
  "results_dir": "results",
  "extra_metrics": "scripts/extra_metrics.py",   # optional, eval_split.py --extra
  "dashboard_url": "",                    # artifact URL, so later sessions update it
  "entries": [                            # one per scored model, baselines first
    {"name": "reference", "label": "Hosted reference", "role": "baseline"},
    {"name": "local-v2", "label": "local model v2", "role": "candidate",
     "train_log": "runs/v2/train.log"}
  ],
  "history": [                            # what changed and what came out of it
    {"iteration": "v2", "date": "YYYY-MM-DD", "change": "what changed in the data",
     "result": "the one number that moved"}
  ]
}
"""

import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from eval_split import load_examples, summarize  # noqa: E402


def read_train_curve(train_log: Path) -> list[list[float]]:
    """-> [[step, loss], ...] from train_decider.py logs."""
    points = []
    for line in train_log.read_text(encoding="utf-8").splitlines():
        match = re.search(r"\[train\] step (\d+)/\d+ loss ([0-9.]+)", line)
        if match:
            points.append([int(match.group(1)), float(match.group(2))])
    return points


def main() -> None:
    registry_file = Path(sys.argv[1])
    output_file = Path(sys.argv[2])
    base_dir = registry_file.parent
    registry = json.loads(registry_file.read_text(encoding="utf-8"))

    examples_by_id = {
        example["id"]: example
        for example in load_examples(base_dir / registry["data_dir"], split=None)
    }
    extra_module = None
    if registry.get("extra_metrics"):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "extra_metrics", base_dir / registry["extra_metrics"]
        )
        extra_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(extra_module)

    models = []
    for entry in registry["entries"]:
        summary = summarize(
            entry["name"],
            examples_by_id,
            base_dir / registry["results_dir"],
            extra_module,
        )
        curve = (
            read_train_curve(base_dir / entry["train_log"])
            if entry.get("train_log")
            else []
        )
        models.append(
            {
                "label": entry["label"],
                "role": entry["role"],
                "summary": summary,
                "curve": curve,
                "notes": entry.get("notes", ""),
            }
        )

    page_data = {
        "title": registry["title"],
        "lede": registry.get("lede", ""),
        "models": models,
        "history": registry.get("history", []),
        "test_examples": sum(
            1 for example in examples_by_id.values() if example["split"] == "test"
        ),
    }
    template = (Path(__file__).parent / "dashboard_template.html").read_text(
        encoding="utf-8"
    )
    page = template.replace("__TITLE__", html.escape(registry["title"])).replace(
        "__DATA__", json.dumps(page_data, ensure_ascii=False).replace("</", "<\\/")
    )
    output_file.write_text(page, encoding="utf-8")
    print(f"{output_file}: {len(models)} models, {len(page) / 1e3:.0f} kB")


if __name__ == "__main__":
    main()
