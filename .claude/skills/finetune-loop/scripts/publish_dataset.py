"""Publish one data version (and optionally the recordings) to a PRIVATE Hugging Face
dataset repo.

    python publish_dataset.py --repo <user>/<name> --data_dir <workspace>/data/v3 \\
        --version v3 [--recordings_dir <workspace>/recordings] [--card card.md] \\
        [--token_file <workspace>/secrets/hf_token]

Without --token_file the login of the `hf` CLI is used (`hf auth login`).
The same can be done with the CLI alone:
    hf repos create <user>/<name> --type dataset --private --exist-ok
    hf upload <user>/<name> <data_dir> data/<version> --type dataset --include "*.jsonl"

Layout in the repo:
    data/<version>/*.jsonl       the examples, split field inside every line
    recordings/recordings.csv    + recordings/*.wav (only with --recordings_dir)
    README.md                    dataset card (from --card, or a minimal one)
The repo is created private if it does not exist. Every publish is one commit with
the version in its message, so earlier versions stay in the dataset's git history.
"""

import argparse
from pathlib import Path

from huggingface_hub import HfApi


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--data_dir", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--recordings_dir")
    parser.add_argument("--card")
    parser.add_argument("--token_file")
    args = parser.parse_args()

    token = None
    if args.token_file:
        token = Path(args.token_file).read_text(encoding="utf-8").strip()
    api = HfApi(token=token)
    api.create_repo(args.repo, repo_type="dataset", private=True, exist_ok=True)
    if api.repo_info(args.repo, repo_type="dataset").private is not True:
        raise SystemExit(
            f"{args.repo} exists and is PUBLIC. Refusing to upload: "
            "make it private first or pick another name."
        )

    api.upload_folder(
        repo_id=args.repo,
        repo_type="dataset",
        folder_path=args.data_dir,
        path_in_repo=f"data/{args.version}",
        allow_patterns=["*.jsonl"],
        commit_message=f"data {args.version}",
    )
    if args.recordings_dir:
        api.upload_folder(
            repo_id=args.repo,
            repo_type="dataset",
            folder_path=args.recordings_dir,
            path_in_repo="recordings",
            allow_patterns=["*.csv", "*.wav"],
            commit_message=f"recordings with data {args.version}",
        )
    if args.card:
        card = Path(args.card).read_text(encoding="utf-8")
    else:
        card = f"# {args.repo}\n\nPrivate fine-tuning data. Latest: {args.version}.\n"
    api.upload_file(
        path_or_fileobj=card.encode("utf-8"),
        path_in_repo="README.md",
        repo_id=args.repo,
        repo_type="dataset",
        commit_message=f"card for {args.version}",
    )
    dataset_url = f"https://huggingface.co/datasets/{args.repo}"
    print(f"published {args.version} to {dataset_url} (private)")


if __name__ == "__main__":
    main()
