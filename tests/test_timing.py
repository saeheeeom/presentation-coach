import pytest

from backend.timing import FINISHED, RUNNING, STOPPED, InvalidTransition, PracticeSession


def make():
    return PracticeSession([10.0, 20.0, 30.0])


def test_full_clean_run():
    s = make()
    s.start(100)
    s.advance(111)
    s.advance(130)
    s.advance(162)
    assert s.state == FINISHED
    assert s.durations == [11, 19, 32]
    assert s.elapsed(999) == 62


def test_stop_and_resume_rolls_back_to_last_good_segment():
    s = make()
    s.start(0)
    s.advance(10)          # segment 0 done in 10s
    s.stop(25)             # stumbled 15s into segment 1
    assert s.state == STOPPED
    assert s.current == 1
    assert s.elapsed(40) == 10  # clock frozen at end of segment 0

    s.resume(100)          # long break doesn't count
    assert s.elapsed(105) == 15
    s.advance(118)
    assert s.durations[1] == 18
    assert [a.status for a in s.attempts] == ["completed", "aborted", "completed"]
    assert s.snapshot(118)["segments"][1]["tries"] == 2


def test_rewind_discards_previous_segment():
    s = make()
    s.start(0)
    s.advance(10)
    s.advance(30)
    s.rewind(35)           # while running segment 2: redo segment 1
    assert s.state == STOPPED
    assert s.current == 1
    assert s.durations == [10, None, None]
    assert s.elapsed(50) == 10
    assert [a.status for a in s.attempts] == ["completed", "discarded", "aborted"]


def test_rewind_after_finish_and_at_start():
    s = PracticeSession([5.0])
    s.start(0)
    s.rewind(2)            # nothing to rewind to: just stops
    assert (s.state, s.current) == (STOPPED, 0)
    s.resume(10)
    s.advance(15)
    assert s.state == FINISHED
    s.rewind(20)
    assert (s.state, s.current, s.durations) == (STOPPED, 0, [None])


def test_invalid_transitions():
    s = make()
    with pytest.raises(InvalidTransition):
        s.advance(0)
    s.start(0)
    with pytest.raises(InvalidTransition):
        s.start(1)
    with pytest.raises(InvalidTransition):
        s.resume(1)
    s.stop(2)
    with pytest.raises(InvalidTransition):
        s.stop(3)


def test_snapshot_reports_live_attempt():
    s = make()
    s.start(0)
    snap = s.snapshot(4.5)
    assert snap["state"] == RUNNING
    assert snap["attempt_elapsed"] == 4.5
    assert snap["total_target"] == 60.0


def test_empty_session_rejected():
    with pytest.raises(ValueError):
        PracticeSession([])
