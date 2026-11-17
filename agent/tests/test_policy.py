import unittest
from workstation_power_agent.main import Snapshot, decide
class Policy(unittest.TestCase):
 def test_gaming(self): self.assertEqual(decide(Snapshot("running","stopped",False,False,999),300),"gaming_vm_running")
 def test_unknown(self): self.assertEqual(decide(Snapshot("stopped","unknown",False,False,999),300),"vm_state_unknown")
 def test_idle(self): self.assertIsNone(decide(Snapshot("stopped","stopped",False,False,300),300))
