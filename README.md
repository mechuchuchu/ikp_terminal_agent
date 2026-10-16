# IKP terminal research prototype

This prototype gives an OpenAI model one custom `run_terminal` function. The host
process handles OpenAI API calls; shell commands run in a separate Docker container
with no API key and only a per-run workspace mounted. The host removes the key from
its environment after creating the API client, so Docker CLI subprocesses do not
inherit it. It does not enable OpenAI's
built-in web-search tool.

The sample tasks are a reproducible random sample of five questions from
`/root/ikp/data/probes/final_probe_set_v8.json`. `tasks/tasks.json` is sent to the
model. `tasks/answer_key.json` stays in the host-side project and is only copied to
the result after the model finishes.

## Setup

From this directory:

```bash
uv pip install -r requirements.txt
docker build -t ikp-terminal-agent:latest .
export OPENAI_API_KEY='your-key'
```

Select a different random task sample with:

```bash
uv run python select_tasks.py --count 5 --seed 20261016
```

Run one task with a model available to your API project:

```bash
uv run python agent.py --task task-01 --model YOUR_MODEL_ID
```

Set `CONTAINER_ENGINE=podman` to use a compatible Podman installation.

## Prototype limits

- The terminal follows the `robots.txt` instruction in the system prompt; this first
  version records commands for later review but does not enforce robots rules itself.
- Commands have a 30-second default timeout, tool calls are capped at 15 per task,
  and model-visible command output is clipped at 16,000 characters.
- The container can access the public internet. This prototype does not yet filter
  private-network destinations or enforce a per-request HTTP budget.
- Each task run gets a fresh workspace. The run trace and answer are saved under
  `runs/`; these files are ignored by Git.

