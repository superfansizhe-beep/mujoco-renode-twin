"""Checks for the explicit physical-release audit registry."""

from cad_modeling.release_gate import RELEASE_ITEMS, is_releasable, render_report


def test_release_items_are_unique_and_actionable():
    keys = [item.key for item in RELEASE_ITEMS]
    assert len(keys) == len(set(keys))
    assert all(item.status and item.source and item.action for item in RELEASE_ITEMS)


def test_release_gate_stays_closed_while_measurements_are_pending():
    assert not is_releasable()


def test_release_report_identifies_the_high_risk_interfaces():
    report = render_report()
    for key in ("wheel_size_and_hub", "connectors_and_harness", "motor_driver_thermal"):
        assert key in report


def main() -> int:
    tests = [
        test_release_items_are_unique_and_actionable,
        test_release_gate_stays_closed_while_measurements_are_pending,
        test_release_report_identifies_the_high_risk_interfaces,
    ]
    failed = 0
    for test in tests:
        try:
            test()
            print(f"PASS {test.__name__}")
        except Exception as exc:
            failed += 1
            print(f"FAIL {test.__name__}: {exc}")
    print(f"{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
