#!/usr/bin/env python3
"""Select a reproducible random sample of IKP probes as terminal research tasks."""

import argparse
import json
import random
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEFAULT_SOURCE = ROOT.parent / "ikp" / "data" / "probes" / "final_probe_set_v8.json"
TASKS_DIR = ROOT / "tasks"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--seed", type=int, default=20261016)
    args = parser.parse_args()

    probes = json.loads(args.source.read_text(encoding="utf-8"))
    if args.count < 1 or args.count > len(probes):
        parser.error(f"--count must be between 1 and {len(probes)}")

    selected = random.Random(args.seed).sample(probes, args.count)
    tasks = []
    answer_key = {}
    for index, probe in enumerate(selected, start=1):
        task_id = f"task-{index:02d}"
        tasks.append({"task_id": task_id, "question": probe["question"]})
        answer_key[task_id] = {
            "probe_id": probe["id"],
            "tier": probe["tier"],
            "domain": probe.get("domain", ""),
            "gold_answer": probe["answer"],
        }

    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    (TASKS_DIR / "tasks.json").write_text(
        json.dumps({"seed": args.seed, "tasks": tasks}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (TASKS_DIR / "answer_key.json").write_text(
        json.dumps(answer_key, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(tasks)} tasks using seed {args.seed} to {TASKS_DIR}")


if __name__ == "__main__":
    main()

