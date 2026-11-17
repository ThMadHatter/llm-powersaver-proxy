#!/usr/bin/env python3
import argparse,json,socket,subprocess,sys,time,urllib.error,urllib.request
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent));from envfile import load
class Error(RuntimeError):pass
class Doctor:
 def __init__(self,e,quick):self.e=e;self.quick=quick;self.ok=0
 def say(self,n,x):self.ok+=1;print(f'[PASS] {n}: {x}',flush=True)
 def run(self,c,t=20):return subprocess.run(c,text=True,capture_output=True,timeout=t)
 def ssh(self,c,t=20):e=self.e;return self.run(['ssh','-p',e['POWER_SSH_PORT'],'-o','BatchMode=yes','-o','ConnectTimeout=5',f"{e['POWER_SSH_USER']}@{e['POWER_HOST']}",c],t)
 def online(self):
  try:return self.ssh('true',8).returncode==0
  except:return False
 def wait(self,want,timeout,name):
  end=time.time()+timeout
  while time.time()<end:
   if self.online()==want:self.say(name,'SSH '+('online' if want else 'offline'));return
   print(f'       {name}: restano {int(end-time.time())}s',flush=True);time.sleep(3)
  raise Error(name+' timeout')
 def wol(self):
  e=self.e;p=bytes.fromhex('FF'*6+e['GAMING_MAC'].replace(':','')*16)
  with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as s:s.setsockopt(socket.SOL_SOCKET,socket.SO_BROADCAST,1);s.sendto(p,(e['GAMING_BROADCAST'],int(e.get('GAMING_WOL_PORT','9'))))
  self.say('WoL','Magic Packet inviato')
 def wake_until_online(self,timeout,name='Boot finale'):
  time.sleep(10);end=time.time()+timeout;attempt=0
  while time.time()<end and not self.online():
   attempt+=1;self.wol();print(f'       {name}: Magic Packet {attempt}, restano {max(0,int(end-time.time()))}s',flush=True);time.sleep(10)
  if not self.online():raise Error(name+' timeout')
  self.say(name,'SSH online')
 def api(self,m,p,auth=True):
  h=f"-H 'Authorization: Bearer {self.e['AGENT_TOKEN']}'" if auth else '';r=self.ssh(f"curl -sS -o /tmp/doctor.body -w '%{{http_code}}' -X {m} {h} http://127.0.0.1:{self.e['AGENT_PORT']}{p}");b=self.ssh('cat /tmp/doctor.body 2>/dev/null||true').stdout.strip();return r.stdout.strip(),b
 def go(self):
  e=self.e;req=['ROUTER_API_KEY','PROXMOX_BASE_URL','PROXMOX_VMID','PROXMOX_TOKEN_ID','PROXMOX_TOKEN_SECRET','GAMING_MAC','GAMING_BROADCAST','POWER_HOST','POWER_SSH_USER','POWER_SSH_PORT','POWER_GAMING_VMID','POWER_LLM_VMID','AGENT_PORT','AGENT_TOKEN','AGENT_BASE_URL','AGENT_HEARTBEAT_PATH','AGENT_HEARTBEAT_INTERVAL','POWER_BOOT_TIMEOUT','POWER_SHUTDOWN_TIMEOUT'];miss=[x for x in req if not e.get(x)]
  if miss:raise Error('variabili mancanti: '+','.join(miss))
  if not self.quick and e.get('POWER_CYCLE_TEST','false').lower()!='true':raise Error('impostare POWER_CYCLE_TEST=true')
  self.say('Configurazione','.env completo')
  if self.run(['systemctl','is-active','litellm-router.service']).stdout.strip()!='active':raise Error('router systemd non active')
  self.say('Router systemd','active')
  with urllib.request.urlopen(f"http://127.0.0.1:{e.get('LISTEN_PORT','8080')}/health/live",timeout=5) as r:self.say('Router liveness','HTTP '+str(r.status))
  try:urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{e.get('LISTEN_PORT','8080')}/v1/models",headers={'Authorization':'Bearer wrong'}),timeout=5);raise Error('token router errato accettato')
  except urllib.error.HTTPError as x:
   if x.code!=401:raise
  self.say('Router auth','HTTP 401')
  if not self.online():self.wol();self.wait(True,int(e['POWER_BOOT_TIMEOUT']),'Boot iniziale')
  else:self.say('SSH','host online')
  if self.ssh("command -v python3 qm systemctl curl tar >/dev/null&&systemctl is-enabled --quiet workstation-power-agent&&systemctl is-active --quiet workstation-power-agent").returncode:raise Error('prerequisiti/agent falliti')
  self.say('Agent','prerequisiti, enabled, active')
  c,b=self.api('GET','/health',False)
  if c!='200':raise Error('health agent '+c)
  self.say('Agent health',b)
  c,_=self.api('GET','/status',False)
  if c!='401':raise Error('auth agent atteso 401, ottenuto '+c)
  self.say('Agent auth','HTTP 401')
  c,_=self.api('POST','/wakelock');c,b=self.api('GET','/status')
  if 'manual_wakelock' not in b:raise Error('blocker wakelock assente')
  self.say('Wakelock','blocker verificato');self.api('DELETE','/wakelock')
  self.api('POST','/activity/llm');c,b=self.api('GET','/status')
  if 'llm_active' not in b:raise Error('blocker heartbeat assente')
  self.say('Heartbeat','blocker verificato');self.ssh('rm -f /run/workstation-power-agent/llm-active-until /run/workstation-power-agent/wakelock')
  vm=e['PROXMOX_VMID'];before=self.ssh(f'qm status {vm}').stdout.strip().split()[-1]
  if before!='running':
   if self.ssh(f'qm start {vm}',60).returncode:raise Error('qm start fallito')
  end=time.time()+90
  while time.time()<end and not self.ssh(f'qm status {vm}').stdout.strip().endswith('running'):time.sleep(3)
  if not self.ssh(f'qm status {vm}').stdout.strip().endswith('running'):raise Error('VM non running')
  self.say('VM LLM',f'{vm} running')
  if self.quick:print(f'\nPASS: TUTTE LE FUNZIONI OPERATIVE ({self.ok} controlli)');return
  if before=='running':raise Error('VM era gia running: power-cycle rifiutato')
  self.ssh(f'qm shutdown {vm} --timeout 60||qm stop {vm}',90)
  end=time.time()+75
  while time.time()<end and not self.ssh(f'qm status {vm}').stdout.strip().endswith('stopped'):time.sleep(3)
  self.say('VM LLM stop',f'{vm} stopped')
  c,b=self.api('POST','/shutdown')
  if c not in ('202','0'):raise Error('shutdown HTTP '+c+' '+b)
  self.wait(False,int(e['POWER_SHUTDOWN_TIMEOUT']),'Poweroff');self.wake_until_online(int(e['POWER_BOOT_TIMEOUT']))
  if self.ssh('systemctl is-active --quiet workstation-power-agent').returncode:raise Error('agent non active dopo boot')
  self.say('Persistenza agent','active dopo reboot');print(f'\nPASS: TUTTE LE FUNZIONI OPERATIVE ({self.ok} controlli)')
def main():
 p=argparse.ArgumentParser();p.add_argument('--env-file',default='router/.env');p.add_argument('--quick',action='store_true');a=p.parse_args()
 try:Doctor(load(a.env_file),a.quick).go()
 except Exception as x:print(f'\nFAIL: {x}',flush=True);raise SystemExit(1)
if __name__=='__main__':main()
