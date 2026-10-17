"""Practice-run state machine: per-segment timing and resume-from-last-good.

All methods take the current time explicitly (seconds, monotonic) so the
logic is deterministic in tests. In Phase 1 the user's button presses drive
advance/stop; in Phase 2 the live aligner calls the same methods.

Timeline semantics:
- The run clock only counts time spent in segments that were completed.
- stop() abandons the in-progress attempt (recorded as "aborted").
- resume() restarts the first unfinished segment, with the run clock set to
  the cumulative time of the completed segments before it.
- rewind() additionally discards the last completed segment, for when the
  speaker realizes it went badly.
"""

from __future__ import annotations

from dataclasses import dataclass, field

IDLE, RUNNING, STOPPED, FINISHED = "idle", "running", "stopped", "finished"


class InvalidTransition(Exception):
    pass


@dataclass
class Attempt:
    segment: int
    start: float  # run-clock time when the attempt began
    duration: float
    status: str  # "completed" | "aborted" | "discarded"


@dataclass
class PracticeSession:
    targets: list[float]
    state: str = IDLE
    current: int = 0
    durations: list[float | None] = field(default_factory=list)
    attempts: list[Attempt] = field(default_factory=list)
    _attempt_started_at: float | None = None  # wall clock of in-progress attempt

    def __post_init__(self) -> None:
        if not self.targets:
            raise ValueError("a session needs at least one segment")
        self.durations = [None] * len(self.targets)

    # --- clock -----------------------------------------------------------
    def base_elapsed(self) -> float:
        """Run-clock time at the start of the current segment."""
        return sum(d for d in self.durations[: self.current] if d is not None)

    def attempt_elapsed(self, now: float) -> float:
        if self.state != RUNNING or self._attempt_started_at is None:
            return 0.0
        return now - self._attempt_started_at

    def elapsed(self, now: float) -> float:
        return self.base_elapsed() + self.attempt_elapsed(now)

    # --- transitions -----------------------------------------------------
    def _require(self, *states: str) -> None:
        if self.state not in states:
            raise InvalidTransition(f"cannot do that while {self.state}")

    def _begin_attempt(self, now: float) -> None:
        self.state = RUNNING
        self._attempt_started_at = now

    def _end_attempt(self, now: float, status: str) -> float:
        duration = now - self._attempt_started_at
        self.attempts.append(Attempt(self.current, self.base_elapsed(), duration, status))
        self._attempt_started_at = None
        return duration

    def start(self, now: float) -> None:
        self._require(IDLE)
        self._begin_attempt(now)

    def advance(self, now: float) -> None:
        """Mark the current segment delivered and move to the next."""
        self._require(RUNNING)
        self.durations[self.current] = self._end_attempt(now, "completed")
        self.current += 1
        if self.current == len(self.targets):
            self.state = FINISHED
        else:
            self._begin_attempt(now)

    def stop(self, now: float) -> None:
        """Speaker made a mistake: abandon the in-progress segment."""
        self._require(RUNNING)
        self._end_attempt(now, "aborted")
        self.state = STOPPED

    def resume(self, now: float) -> None:
        """Restart from the segment after the last fully delivered one."""
        self._require(STOPPED)
        self._begin_attempt(now)

    def rewind(self, now: float) -> None:
        """Also redo the previous segment (the last 'good' one wasn't)."""
        self._require(RUNNING, STOPPED, FINISHED)
        if self.state == RUNNING:
            self._end_attempt(now, "aborted")
        if self.current == 0:
            self.state = STOPPED
            return
        self.current -= 1
        for attempt in reversed(self.attempts):
            if attempt.segment == self.current and attempt.status == "completed":
                attempt.status = "discarded"
                break
        self.durations[self.current] = None
        self.state = STOPPED

    # --- reporting -------------------------------------------------------
    def snapshot(self, now: float) -> dict:
        return {
            "state": self.state,
            "current": self.current,
            "base_elapsed": round(self.base_elapsed(), 3),
            "attempt_elapsed": round(self.attempt_elapsed(now), 3),
            "total_target": round(sum(self.targets), 1),
            "segments": [
                {
                    "target": t,
                    "actual": None if d is None else round(d, 2),
                    "tries": sum(1 for a in self.attempts if a.segment == i),
                }
                for i, (t, d) in enumerate(zip(self.targets, self.durations))
            ],
        }
