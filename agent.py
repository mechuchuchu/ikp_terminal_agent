#!/usr/bin/env python3
"""Run one IKP factual-research task with OpenAI Responses API and Docker terminal access."""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from openai import OpenAI

from terminal import DockerTerminal


ROOT = Path(__file__).resolve().parent
TASKS_FILE = ROOT / "tasks" / "tasks.json"
ANSWER_KEY_FILE = ROOT / "tasks" / "answer_key.json"
PROMPT_FILE = ROOT / "system_prompt.txt"
RUNS_DIR = ROOT / "runs"
MAX_OUTPUT_CHARS = 16000

TOOLS = [
    {
        "type": "function",
        "name": "run_terminal",
        "description": (
            "Run one shell command in the task's temporary Docker workspace. "
            "Use ordinary terminal commands such as curl, wget, python, and grep."
        ),
        "parameters": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
            "additionalProperties": False,
        },
        "strict": True,
    }
]


def append_jsonl(path: Path, item: dict):
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", required=True, help="Task ID, e.g. task-01")
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL"),
                        help="OpenAI model ID (or set OPENAI_MODEL)")
    parser.add_argument("--max-calls", type=int, default=15)
    parser.add_argument("--command-timeout", type=int, default=30)
    args = parser.parse_args()
    if not args.model:
        parser.error("pass --model or set OPENAI_MODEL")
    if args.max_calls < 1 or args.command_timeout < 1:
        parser.error("call and timeout limits must be positive")

    tasks_data = json.loads(TASKS_FILE.read_text(encoding="utf-8"))
    task = next((row for row in tasks_data["tasks"] if row["task_id"] == args.task), None)
    if task is None:
        parser.error(f"unknown task {args.task!r}; available: " +
                     ", ".join(row["task_id"] for row in tasks_data["tasks"]))
    answer_key = json.loads(ANSWER_KEY_FILE.read_text(encoding="utf-8"))[args.task]

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + args.task
    run_dir = RUNS_DIR / run_id
    workspace = run_dir / "workspace"
    run_dir.mkdir(parents=True, exist_ok=False)
    trace_file = run_dir / "trace.jsonl"

    instructions = PROMPT_FILE.read_text(encoding="utf-8")
    user_input = (
        f"Task ID: {task['task_id']}\n"
        f"Question: {task['question']}\n\n"
        "Investigate this question using the terminal. Return your answer with source URLs "
        "and short supporting excerpts."
    )

    # Keep the credential in the host API client only. Docker CLI subprocesses must
    # not inherit it, and the task container is never started with an env key.
    api_key = os.environ.pop("OPENAI_API_KEY", None)
    if not api_key:
        parser.error("set OPENAI_API_KEY in the host environment")
    client = OpenAI(api_key=api_key)
    terminal = DockerTerminal(workspace, timeout_seconds=args.command_timeout)
    terminal.start()
    calls_used = 0
    started_at = time.monotonic()
    final_text = ""

    try:
        response = client.responses.create(
            model=args.model,
            instructions=instructions,
            input=user_input,
            tools=TOOLS,
        )

        while True:
            function_calls = [item for item in response.output if item.type == "function_call"]
            if not function_calls:
                final_text = response.output_text or ""
                break

            outputs = []
            budget_exhausted = False
            for call in function_calls:
                if call.name != "run_terminal":
                    output_text = f"Unsupported tool: {call.name}"
                elif calls_used >= args.max_calls:
                    budget_exhausted = True
                    output_text = "Terminal call budget reached. Give your best evidence-based final answer now."
                else:
                    call_args = json.loads(call.arguments)
                    command = call_args["command"]
                    calls_used += 1
                    command_started = time.monotonic()
                    result = terminal.run(command)
                    output_text = json.dumps(result, ensure_ascii=False)
                    append_jsonl(trace_file, {
                        "at": datetime.now(timezone.utc).isoformat(),
                        "type": "terminal_call",
                        "call_id": call.call_id,
                        "command": command,
                        "elapsed_seconds": round(time.monotonic() - command_started, 3),
                        **result,
                    })

                outputs.append({
                    "type": "function_call_output",
                    "call_id": call.call_id,
                    "output": output_text[:MAX_OUTPUT_CHARS],
                })

            response = client.responses.create(
                model=args.model,
                previous_response_id=response.id,
                instructions=instructions,
                input=outputs,
                tools=[] if budget_exhausted else TOOLS,
            )

        elapsed = round(time.monotonic() - started_at, 3)
        result_record = {
            "run_id": run_id,
            "task_id": task["task_id"],
            "question": task["question"],
            "model": args.model,
            "tool_calls": calls_used,
            "elapsed_seconds": elapsed,
            "answer": final_text,
            "answer_key": answer_key,
        }
        (run_dir / "result.json").write_text(
            json.dumps(result_record, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        append_jsonl(trace_file, {
            "at": datetime.now(timezone.utc).isoformat(),
            "type": "final",
            "response_id": response.id,
            "answer": final_text,
            "elapsed_seconds": elapsed,
        })
        print(final_text)
        print(f"\nSaved run to {run_dir}")
    finally:
        terminal.stop()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        raise SystemExit(130)

