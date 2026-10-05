"""Fine-tune a Jev-style decision model (Mapika/decider family) on examples in the
System One format.

    python train_decider.py --data_dir <workspace>/data/v3 \\
        --base_model Mapika/decider-0.8b --out <workspace>/runs/v3
    # smoke test (memory, speed, does backward work on this OS):
    python train_decider.py ... --max_steps 5
    # share the GPU with a game:
    python train_decider.py ... --adam_8bit --freeze_embeddings \\
        --max_tokens 2048 --accum 16 --gpu_memory_share 0.6 --gpu_busy_share 0.6

Input: every *.jsonl in --data_dir, one example per line:
    {"id", "kind", "split": "train"|"test", "state": {...} | "text",
     "questions": {id: System One question}, "gold": {id: bool | option}}
Only split == "train" is used. Every question becomes its own row (state + one
question), exactly how decider's system_one asks at inference, so training and
inference see the same prompt.
Gold for a noul question is a bool. Gold for a choice question is the option name.
"""

import argparse
import json
import math
import random
import shutil
import time
from pathlib import Path

import torch
from decider.data.core import Example, Q
from decider.model import DecisionModel, collate
from decider.systemone import render_question, render_state
from decider.train import batches_by_tokens, loss_fn, make_items
from huggingface_hub import snapshot_download


def gold_index(rendered_question: dict, gold) -> int:
    """noul options are [no, yes]; choice options follow the question's own names."""
    if rendered_question["type"] == "noul":
        return 1 if gold else 0
    return rendered_question["names"].index(gold)


def load_train_rows(data_dir: Path) -> list[Example]:
    rows = []
    for data_file in sorted(data_dir.glob("*.jsonl")):
        for line in data_file.read_text(encoding="utf-8").splitlines():
            example = json.loads(line)
            if example["split"] != "train":
                continue
            context = render_state(example["state"])
            for question_id, question in example["questions"].items():
                rendered = render_question(question)
                gold = gold_index(rendered, example["gold"][question_id])
                rows.append(
                    Example(
                        context,
                        [Q(rendered["question"], rendered["options"], gold)],
                        example["kind"],
                    )
                )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data_dir", required=True)
    parser.add_argument(
        "--base_model",
        default="Mapika/decider-0.8b",
        help="HF id or a local folder (e.g. an earlier run)",
    )
    parser.add_argument("--out", required=True)
    parser.add_argument("--epochs", type=float, default=1.0)
    parser.add_argument("--lr", type=float, default=1e-5)
    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument(
        "--max_tokens", type=int, default=8192, help="tokens per micro-batch"
    )
    parser.add_argument("--accum", type=int, default=4)
    parser.add_argument(
        "--max_steps", type=int, default=0, help="stop early (smoke test)"
    )
    parser.add_argument(
        "--freeze_embeddings",
        action="store_true",
        help="do not train the vocabulary matrix: ~0.7 GB less VRAM on 0.8B",
    )
    parser.add_argument(
        "--adam_8bit",
        action="store_true",
        help="8-bit AdamW states (bitsandbytes): ~4x smaller optimizer state",
    )
    parser.add_argument(
        "--gpu_memory_share",
        type=float,
        default=1.0,
        help="hard VRAM cap for this process, 0.6 = 60%%",
    )
    parser.add_argument(
        "--gpu_busy_share",
        type=float,
        default=1.0,
        help="rest after every micro-batch so the GPU works only this share of time",
    )
    args = parser.parse_args()
    if args.gpu_memory_share < 1.0:
        torch.cuda.set_per_process_memory_fraction(args.gpu_memory_share)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    log_file = (out_dir / "train.log").open("a", encoding="utf-8")

    def log(message: str) -> None:
        print(message, flush=True)
        log_file.write(message + "\n")
        log_file.flush()

    base_model_dir = (
        Path(args.base_model)
        if Path(args.base_model).exists()
        else Path(snapshot_download(args.base_model))
    )
    log(f"[args] {json.dumps(vars(args))} base_dir={base_model_dir}")
    (out_dir / "train_config.json").write_text(
        json.dumps(vars(args), indent=2), encoding="utf-8"
    )

    rng = random.Random(0)
    torch.manual_seed(0)
    rows = load_train_rows(Path(args.data_dir))
    model = DecisionModel(str(base_model_dir)).cuda()
    if args.freeze_embeddings:
        model.lm.get_input_embeddings().weight.requires_grad_(False)
    trained_parameters = [
        parameter for parameter in model.parameters() if parameter.requires_grad
    ]

    items = make_items(rows, model.tok, rng, max_ctx=1536)
    steps_per_epoch = math.ceil(
        len(batches_by_tokens(items, args.max_tokens, random.Random(0))) / args.accum
    )
    total_steps = args.max_steps or int(steps_per_epoch * args.epochs)
    token_millions = sum(len(item["ids"]) for item in items) / 1e6
    log(
        f"[data] {len(rows)} rows, {token_millions:.1f}M tokens, "
        f"{total_steps} optimizer steps"
    )

    if args.adam_8bit:
        import bitsandbytes

        optimizer = bitsandbytes.optim.AdamW8bit(
            trained_parameters, lr=args.lr, weight_decay=0.0, betas=(0.9, 0.95)
        )
    else:
        optimizer = torch.optim.AdamW(
            trained_parameters, lr=args.lr, weight_decay=0.0, betas=(0.9, 0.95)
        )

    def learning_rate(step: int) -> float:
        if step < args.warmup:
            return args.lr * step / args.warmup
        progress = min(1.0, (step - args.warmup) / max(1, total_steps - args.warmup))
        return args.lr * 0.5 * (1 + math.cos(math.pi * progress))

    model.train()
    step = micro_step = 0
    loss_sum = loss_count = 0
    start = time.time()
    while step < total_steps:
        for batch_indexes in batches_by_tokens(items, args.max_tokens, rng):
            if step >= total_steps:
                break
            work_started = time.perf_counter()
            batch = collate(
                [items[index] for index in batch_indexes], model.tok.pad_token_id
            )
            batch = {
                key: (value.cuda() if torch.is_tensor(value) else value)
                for key, value in batch.items()
            }
            loss, cross_entropy = loss_fn(model(batch), batch["golds"], batch["nopts"])
            (loss / args.accum).backward()
            # .item() waits for the GPU, so the work time measured below is real
            loss_sum += cross_entropy.item()
            loss_count += 1
            micro_step += 1
            if args.gpu_busy_share < 1.0:
                time.sleep(
                    (time.perf_counter() - work_started)
                    * (1 - args.gpu_busy_share)
                    / args.gpu_busy_share
                )
            if micro_step % args.accum == 0:
                for group in optimizer.param_groups:
                    group["lr"] = learning_rate(step)
                torch.nn.utils.clip_grad_norm_(trained_parameters, 1.0)
                optimizer.step()
                optimizer.zero_grad(set_to_none=True)
                step += 1
                if step % 10 == 0 or step == total_steps or args.max_steps:
                    minutes = (time.time() - start) / 60
                    eta_minutes = minutes / step * (total_steps - step)
                    peak_gb = torch.cuda.max_memory_allocated() / 1e9
                    log(
                        f"[train] step {step}/{total_steps} "
                        f"loss {loss_sum / loss_count:.4f} "
                        f"lr {learning_rate(step):.2e} {minutes:.1f} min, "
                        f"eta {eta_minutes:.0f} min, peak memory {peak_gb:.1f} GB"
                    )
                    loss_sum = loss_count = 0

    model_dir = out_dir / "model"
    model.lm.save_pretrained(model_dir)
    model.tok.save_pretrained(model_dir)
    for file_name in ("decider_config.json", "chat_template.jinja"):
        if (base_model_dir / file_name).exists():
            shutil.copy(base_model_dir / file_name, model_dir / file_name)
    log(f"[done] saved {model_dir} after {(time.time() - start) / 60:.1f} min")


if __name__ == "__main__":
    main()
