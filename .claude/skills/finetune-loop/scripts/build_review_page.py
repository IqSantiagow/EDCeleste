"""Build the data review page (one HTML file) that the user reads BEFORE any training
starts.

    python build_review_page.py --data_dir <workspace>/data/v3 \\
        --out <workspace>/data/v3/review.html \\
        --title "Training data v3" [--intro intro.html]

Shows: counts per kind and split, the share of "yes" per question text (spots
questions that are always yes or always no, which the model would learn as a
constant), and every example with filters.
--intro is an HTML snippet with the project-specific part: what changed, open
decisions, findings.
"""

import argparse
import collections
import html
import json
from pathlib import Path


def short_example(example: dict) -> dict:
    state = example["state"]
    state_text = (
        state
        if isinstance(state, str)
        else json.dumps(state, ensure_ascii=False, indent=1)
    )
    answers = []
    for question_id, question in example["questions"].items():
        gold = example["gold"][question_id]
        answers.append(
            [
                question.get("instructions") or question_id,
                gold if isinstance(gold, str) else bool(gold),
            ]
        )
    return {
        "id": example["id"],
        "kind": example["kind"],
        "split": example["split"],
        "group": example.get("situation", ""),
        "state": state_text,
        "answers": answers,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data_dir", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--title", default="Training data")
    parser.add_argument("--intro", help="HTML snippet shown under the header")
    args = parser.parse_args()

    examples = []
    for data_file in sorted(Path(args.data_dir).glob("*.jsonl")):
        examples += [
            json.loads(line)
            for line in data_file.read_text(encoding="utf-8").splitlines()
        ]

    counts = collections.Counter(
        (example["kind"], example["split"]) for example in examples
    )
    count_rows = "".join(
        f"<tr><td><b>{html.escape(kind)}</b></td>"
        f"<td class='n'>{counts[kind, 'train']}</td>"
        f"<td class='n'>{counts[kind, 'test']}</td></tr>"
        for kind in sorted({kind for kind, _ in counts})
    )
    yes_by_question = collections.defaultdict(list)
    for example in examples:
        for question_id, question in example["questions"].items():
            gold = example["gold"][question_id]
            if isinstance(gold, bool):
                yes_by_question[
                    (example["kind"], question.get("instructions") or question_id)
                ].append(gold)
    question_rows = "".join(
        f"<tr><td>{html.escape(kind)}</td><td>{html.escape(text[:160])}</td>"
        f"<td class='n'>{sum(answers) / len(answers):.0%}</td>"
        f"<td class='n'>{len(answers)}</td></tr>"
        for (kind, text), answers in sorted(
            yes_by_question.items(), key=lambda item: sum(item[1]) / len(item[1])
        )
    )
    intro = Path(args.intro).read_text(encoding="utf-8") if args.intro else ""

    template = (Path(__file__).parent / "review_template.html").read_text(
        encoding="utf-8"
    )
    replacements = {
        "__TITLE__": html.escape(args.title),
        "__INTRO__": intro,
        "__TOTAL__": str(len(examples)),
        "__COUNT_ROWS__": count_rows,
        "__QUESTION_ROWS__": question_rows,
        "__EXAMPLES_JSON__": json.dumps(
            [short_example(example) for example in examples], ensure_ascii=False
        ).replace("</", "<\\/"),
    }
    for placeholder, value in replacements.items():
        template = template.replace(placeholder, value)
    Path(args.out).write_text(template, encoding="utf-8")
    print(f"{args.out}: {len(examples)} examples, {len(template) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
