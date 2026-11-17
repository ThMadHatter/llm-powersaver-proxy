import importlib.util, sys, tempfile, types, unittest
from pathlib import Path
SPEC=importlib.util.spec_from_file_location('doctor',Path(__file__).parents[2]/'scripts/doctor.py'); d=importlib.util.module_from_spec(SPEC); sys.modules[SPEC.name]=d; SPEC.loader.exec_module(d)
class DoctorTests(unittest.TestCase):
 def test_env_validation(self):
  with tempfile.TemporaryDirectory() as x:
   p=Path(x)/'.env'; p.write_text('ROUTER_API_KEY=1234567890123456\nGAMING_MAC=AA:BB:CC:DD:EE:FF\n')
   args=types.SimpleNamespace(env_file=str(p)); obj=d.Doctor(args); obj.load_env()
   self.assertTrue(any(c.status=='FAIL' for c in obj.checks)); self.assertTrue(any(c.name=='Wake-on-LAN config' and c.status=='PASS' for c in obj.checks))
