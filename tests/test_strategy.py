import importlib.util
from pathlib import Path
import sys
import unittest

MODULE_PATH = Path(__file__).resolve().parents[1] / "src" / "run.py"
SPEC = importlib.util.spec_from_file_location("alert_run", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MOD = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MOD
SPEC.loader.exec_module(MOD)


class StrategyTests(unittest.TestCase):
    def test_switches_once_and_recovers_at_saved_high(self):
        qqq = {
            "2024-01-01": 100.0,
            "2024-01-02": 110.0,
            "2024-01-03": 99.0,
            "2024-01-04": 95.0,
            "2024-01-05": 109.0,
            "2024-01-06": 110.0,
        }
        tqqq = {
            "2024-01-01": 100.0,
            "2024-01-02": 130.0,
            "2024-01-03": 91.0,
            "2024-01-04": 80.0,
            "2024-01-05": 125.0,
            "2024-01-06": 130.0,
        }
        _, signals, _, _, status = MOD.replay(qqq, tqqq, 0.10, 0.0)
        self.assertEqual([s.action for s in signals], ["SWITCH_TO_TQQQ", "SWITCH_TO_QQQ"])
        self.assertEqual(signals[0].date, "2024-01-03")
        self.assertEqual(signals[0].reference_high, 110.0)
        self.assertEqual(signals[1].date, "2024-01-06")
        self.assertEqual(status["holding"], "QQQ")

    def test_does_not_recover_below_reference_high(self):
        qqq = {"2024-01-01": 100.0, "2024-01-02": 90.0, "2024-01-03": 99.9}
        tqqq = {"2024-01-01": 100.0, "2024-01-02": 70.0, "2024-01-03": 99.0}
        _, signals, _, _, status = MOD.replay(qqq, tqqq, 0.10, 0.0)
        self.assertEqual(len(signals), 1)
        self.assertEqual(status["holding"], "TQQQ")
        self.assertEqual(status["recovery_price"], 100.0)


if __name__ == "__main__":
    unittest.main()
