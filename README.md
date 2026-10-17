# Presentation Practice Coach

Segment-based presentation practice: split a script into segments, time each
one, and restart from the last segment you delivered well. See
[presentation_coach.md](presentation_coach.md) for the full plan.

**Status: Phase 1 (practice core).** Segmentation, per-segment timers, manual
advance/stop/resume, audio recording per run, run history. Live alignment
(Phase 2) and feedback (Phase 3) come next.

## Run it

```bash
uv sync
uv run uvicorn backend.app:app --port 8000
```

Open http://localhost:8000.

### On PACE

Run the server on a compute node and tunnel to it from your laptop. Browsers
only allow microphone access on `localhost` or HTTPS, so open the app through
the tunnel at `localhost`, not the node's hostname.

```bash
# on PACE (login node), grab an interactive node
salloc -N1 --ntasks-per-node=4 -t 2:00:00      # add --gres=gpu:1 for the LLM / Phase 2
hostname                                         # e.g. atl1-1-02-003-5-0
cd presentation-coach && uv run uvicorn backend.app:app --port 8000

# on your laptop
ssh -N -L 8000:<node-hostname>:8000 <gt-username>@login-ice.pace.gatech.edu
# then open http://localhost:8000
```

If port 8000 is taken on the node, pick another one and use it in both commands.

### Optional: local LLM segmentation (free)

```bash
uv sync --extra llm
PC_LLM_MODEL=Qwen/Qwen2.5-1.5B-Instruct uv run uvicorn backend.app:app --port 8000
```

The model only chooses where segment boundaries fall; the wording always comes
from your script. If the model is missing or returns something invalid, the
app falls back to the rule-based splitter. Set `HF_HOME` to a scratch
directory to keep model downloads out of your home quota.

## Practice controls

| Key | Action |
| --- | --- |
| Space | Start / segment done |
| Esc | Stop: I slipped (the current segment is discarded) |
| Enter | Resume from the start of the current segment |
| Backspace | Redo the previous segment too |

The total clock only counts completed segments, so after a stop it resumes
from the cumulative time at the last good segment.

## Layout

```
backend/   app.py (FastAPI), segmenter.py, llm.py, timing.py, store.py
frontend/  index.html, app.js, style.css (no build step)
tests/     pytest suite: uv run pytest
data/      SQLite DB + recorded audio (git-ignored; override with PC_DATA_DIR)
```
