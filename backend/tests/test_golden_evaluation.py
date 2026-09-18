from evals.run_golden import run_golden_set


def test_attachment_golden_set() -> None:
    report = run_golden_set()

    assert report["failed"] == 0, report["results"]
    assert report["passed"] >= 4
