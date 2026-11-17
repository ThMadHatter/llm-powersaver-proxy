import importlib.util, tempfile, types, unittest
from pathlib import Path
S=importlib.util.spec_from_file_location('wizard',Path(__file__).parents[1]/'setup.py'); w=importlib.util.module_from_spec(S); S.loader.exec_module(w)
class Setup(unittest.TestCase):
 def args(self): return types.SimpleNamespace(gaming_vmid=100,llm_vmid=101,enable_poweroff=False,agent_port=8765)
 def test_mac(self): self.assertEqual(w.mac('aa-bb-cc-dd-ee-ff'),'AA:BB:CC:DD:EE:FF')
 def test_bundle(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'x.tgz'; w.bundle(self.args(),p,'x'*32); self.assertGreater(p.stat().st_size,1000)
