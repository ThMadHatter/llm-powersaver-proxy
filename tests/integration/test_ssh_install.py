"""Real SSH integration tests. Opt-in through SSH_TEST_HOST."""
import importlib.util, json, os, secrets, subprocess, types, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
SPEC=importlib.util.spec_from_file_location('wizard',ROOT/'installer/setup.py'); w=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(w)
HOST=os.getenv('SSH_TEST_HOST'); USER=os.getenv('SSH_TEST_USER','root'); PORT=int(os.getenv('SSH_TEST_PORT','22')); AGENT_PORT=int(os.getenv('SSH_TEST_AGENT_PORT','18765'))
@unittest.skipUnless(HOST,'Impostare SSH_TEST_HOST per i test SSH reali')
class SshInstallIntegration(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.args=types.SimpleNamespace(host=HOST,ssh_user=USER,ssh_port=PORT,gaming_vmid=int(os.getenv('SSH_TEST_GAMING_VMID','100')),llm_vmid=int(os.getenv('SSH_TEST_LLM_VMID','101')),agent_port=AGENT_PORT,enable_poweroff=False)
  cls.token=secrets.token_urlsafe(32)
  if not w.ready(cls.args): raise unittest.SkipTest('Target SSH non raggiungibile con chiave non interattiva')
 def remote(self,cmd,check=True): return w.ssh(self.args,cmd,check=check,capture_output=True,timeout=60)
 def test_01_install_and_health(self):
  w.deploy(self.args,self.token)
  self.assertEqual(self.remote('systemctl is-active workstation-power-agent').stdout.strip(),'active')
  health=self.remote(f'curl -fsS http://127.0.0.1:{AGENT_PORT}/health').stdout
  self.assertEqual(json.loads(health)['status'],'ok')
 def test_02_authenticated_status_and_observe_only(self):
  status=self.remote(f"curl -fsS -H 'Authorization: Bearer {self.token}' http://127.0.0.1:{AGENT_PORT}/status").stdout
  payload=json.loads(status); self.assertTrue(payload['observe_only']); self.assertIn('state',payload)
  self.assertNotEqual(self.remote(f'curl -s -o /dev/null -w %{{http_code}} http://127.0.0.1:{AGENT_PORT}/status').stdout.strip(),'200')
 def test_03_update_changes_release(self):
  before=self.remote('readlink -f /opt/workstation-power-agent/current').stdout.strip()
  w.deploy(self.args,self.token)
  after=self.remote('readlink -f /opt/workstation-power-agent/current').stdout.strip()
  self.assertNotEqual(before,after); self.assertEqual(self.remote('systemctl is-active workstation-power-agent').stdout.strip(),'active')
 def test_04_failed_healthcheck_rolls_back(self):
  before=self.remote('readlink -f /opt/workstation-power-agent/current').stdout.strip()
  with self.assertRaises(subprocess.CalledProcessError): w.deploy(self.args,self.token,broken=True)
  after=self.remote('readlink -f /opt/workstation-power-agent/current').stdout.strip()
  self.assertEqual(before,after); self.assertEqual(self.remote('systemctl is-active workstation-power-agent').stdout.strip(),'active')
