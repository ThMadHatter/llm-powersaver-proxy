import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("powersaver_doctor", ROOT / "scripts/doctor.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class RepeatedWolTests(unittest.TestCase):
    def test_final_boot_repeats_wol_until_online(self):
        doctor = module.Doctor({}, False)
        states = iter([False, False, False, True, True])
        doctor.online = lambda: next(states)
        calls = []
        doctor.wol = lambda: calls.append("wol")
        reports = []
        doctor.say = lambda name, detail: reports.append((name, detail))
        ticks = {"value": 0}
        def fake_time():
            ticks["value"] += 1
            return ticks["value"]
        with patch.object(module.time, "sleep", lambda _: None), patch.object(module.time, "time", fake_time):
            doctor.wake_until_online(180)
        self.assertEqual(len(calls), 3)
        self.assertEqual(reports[-1], ("Boot finale", "SSH online"))

if __name__ == "__main__":
    unittest.main()
