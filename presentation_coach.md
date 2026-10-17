# Presentation Practice Coach — Project Plan

Oct 16, 2026 · @Saehee

## Overview

A practice app that splits a presentation script into segments, times each one, and lets the speaker restart from the last segment they delivered well. After each run, it gives feedback a person can act on, not raw acoustic numbers.

It solves two problems with practicing today:

- **One mistake resets the run.** A stumble near the end means restarting the timer from the top, or giving up on accurate timing.
- **Acoustic feedback isn't actionable.** Tools report formant or F0 values, but nobody can act on "raise your F0." Useful feedback names a moment and a behavior: "You paused mid-sentence at 1:32."

## Goals and non-goals

Goals:

- Segment-based practice with per-segment timing and resume from the last good segment
- Real-time alignment of speech to the script
- Feedback on six dimensions, each tied to a specific segment and phrased as a behavior
- Evidence that the metrics track human judgments of presentation quality

Non-goals for v1:

- Languages other than English
- Slide design feedback
- Video or body-language analysis (audio only)

## Core features

1. **Script segmentation.** The user pastes a script, and the app splits it into segments at sentence or paragraph boundaries. Splitting is LLM-assisted and user-editable. Each segment gets a target duration from its word count and the target pace.
2. **Guided practice.** The current segment is shown on screen and advances automatically when the aligner detects its end.
3. **Resume from the last good segment.** When the speaker stops after a mistake, the session rolls back to the start of the segment after the last fully delivered one. The timer resumes from the cumulative time at that point.
4. **Per-segment timer.** Shows actual vs. target time for each segment, and total time vs. the time limit.
5. **Feedback report.** After each run, it lists flagged moments with timestamps linked to their segments, plus trends across runs.

## Evaluation framework

Each metric is computed per segment and turned into a behavior the speaker can change. Raw formant or F0 values are never shown.

| Dimension | What it measures | How it's measured | Example feedback |
| --- | --- | --- | --- |
| Fluency | Fillers, mid-phrase pauses, restarts | STT word timestamps and a filler lexicon; pause location vs. script boundaries | "3 fillers in segment 4; you paused mid-phrase at 1:32" |
| Prosody | Monotone stretches, emphasis, uptalk | F0 and energy variation per segment (Praat via parselmouth); pitch on key words; sentence-final rise | "Segment 2 sounds flat. Stress 'three times faster.'" |
| Pace and timing | Speaking rate and time vs. target | Words per minute per segment; segment durations | "You sped up in the last three segments" |
| Script fidelity | Key points covered, segments skipped | Semantic similarity between spoken and scripted segment | "Segment 5's main point was skipped" |
| Intelligibility | Words a listener may miss | STT vs. script word error rate as a proxy | "'Heterogeneous' was misrecognized twice. Slow down on it." |
| Script quality (before practice) | Sentence complexity, hook, signposting, conclusion | Syntactic complexity measures; LLM rubric | "Split this three-clause sentence before you practice it" |

Pauses at sentence or section boundaries count as good pacing. Only pauses mid-phrase are flagged.

## System architecture

The script aligner is the core: matching live speech to the script tells the tracker when a segment is done, and the same alignment feeds every per-segment metric.

&#91;embedded content: system architecture · 8 components\]

Planned stack:

- **Speech-to-text:** Whisper with word-level timestamps
- **Acoustics:** Praat via parselmouth for F0 and pauses; librosa for energy
- **Script fidelity:** sentence-transformers for semantic matching
- **Feedback and segmentation:** an LLM API
- **App:** Python backend with a web frontend

## Validation plan

The metrics only matter if they track how people judge a talk.

1. Record a set of practice runs from me and volunteers, covering both strong and weak deliveries.
2. Have at least two raters score each run, overall and per dimension, on a 1–5 rubric. Report inter-rater agreement.
3. Compute the Spearman correlation between each metric and the human scores. Drop or reweight metrics that don't correlate.
4. Check whether speakers' human-rated scores improve across sessions when they practice with feedback.

## Milestones

The app is usable for practice after week 4, before any feedback exists.

&#91;embedded content: milestones · 4 phases over 8 weeks\]

Live alignment is the riskiest phase, so it comes second: if it slips, the timer and manual resume still work.

## Risks and open questions

- **Alignment latency.** Streaming STT may lag behind the speaker. Fallback: transcribe in short chunks and fuzzy-match against the script.
- **Ad-libbing breaks alignment.** Match on meaning, not exact words, so paraphrases still advance the segment.
- **STT errors confound intelligibility.** Calibrate against clean reference readings of the same script.
- **Noisy human ratings.** Use a written rubric and multiple raters.

Open questions:

- [ ] Web app or desktop app? This affects mic access and latency.
- [ ] Which STT: local Whisper or a streaming API?
- [ ] Who will rate the recorded runs?
