#!/usr/bin/env python3
import argparse,json,socket,subprocess,sys,time,urllib.error,urllib.request
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent));from envfile import load
class D:
 def __init__(self,e):self.e=e;self.fail=0
 def out(self,s,n,x):print(f'[{s}] {n}: {x}');self.fail+=s=='FAIL'
 def run(self,c,check=False,timeout=20):return subprocess.run(c,text=True,capture_output=True,check=check,timeout=timeout)
 def ssh(self,c,timeout=20):
  e=self.e;return self.run(['ssh','-p',e['POWER_SSH_PORT'],'-o','BatchMode=yes','-o','ConnectTimeout=5','-o','StrictHostKeyChecking=accept-new',f"{e['POWER_SSH_USER']}@{e['POWER_HOST']}",c],timeout=timeout)
 def online(self):return self.ssh('true').returncode==0
 def wait(self,want,timeout):
  end=time.time()+timeout
  while time.time()<end:
   if self.online()==want:return True
   time.sleep(3)
  return False
 def wol(self):
  e=self.e;x=bytes.fromhex('FF'*6+e['GAMING_MAC'].replace(':','')*16)
  with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as s:s.setsockopt(socket.SOL_SOCKET,socket.SO_BROADCAST,1);s.sendto(x,(e.get('GAMING_BROADCAST','255.255.255.255'),int(e.get('GAMING_WOL_PORT','9'))))
 def api(self,method,path,expected):
  e=self.e;h=f"Authorization: Bearer {e['AGENT_TOKEN']}";cmd=f"curl -sS -o /tmp/doctor.body -w '%{{http_code}}' -X {method} -H {json.dumps(h)} http://127.0.0.1:{e['AGENT_PORT']}{path}"
  r=self.ssh(cmd);code=r.stdout.strip();body=self.ssh('cat /tmp/doctor.body').stdout.strip();self.out('PASS' if code in expected else 'FAIL',f'{method} {path}',f'HTTP {code} {body[:160]}');return code,body
 def go(self):
  e=self.e;required=['ROUTER_API_KEY','PROXMOX_BASE_URL','PROXMOX_NODE','PROXMOX_VMID','PROXMOX_TOKEN_ID','PROXMOX_TOKEN_SECRET','GAMING_MAC','GAMING_BROADCAST','POWER_HOST','POWER_SSH_USER','POWER_SSH_PORT','POWER_GAMING_VMID','POWER_LLM_VMID','AGENT_PORT','AGENT_TOKEN','POWER_BOOT_TIMEOUT','POWER_SHUTDOWN_TIMEOUT']
  miss=[x for x in required if not e.get(x)];self.out('FAIL' if miss else 'PASS','Configurazione .env','mancano '+','.join(miss) if miss else 'completa')
  r=self.run(['systemctl','is-active','litellm-router.service']);self.out('PASS' if r.stdout.strip()=='active' else 'FAIL','Router systemd',r.stdout.strip())
  try:
   with urllib.request.urlopen(f"http://127.0.0.1:{e.get('LISTEN_PORT','8080')}/health/live",timeout=5) as x:self.out('PASS','Router liveness',f'HTTP {x.status}')
  except Exception as x:self.out('FAIL','Router liveness',str(x))
  if not self.online():self.wol();self.out('PASS','Wake-on-LAN','Magic Packet inviato');
  if not self.wait(True,int(e['POWER_BOOT_TIMEOUT'])):self.out('FAIL','Boot/SSH','timeout');return
  self.out('PASS','Boot/SSH','host raggiungibile')
  r=self.ssh("command -v python3 qm systemctl curl tar >/dev/null && systemctl is-enabled --quiet workstation-power-agent && systemctl is-active --quiet workstation-power-agent")
  self.out('PASS' if r.returncode==0 else 'FAIL','Prerequisiti e agent',r.stderr.strip() or 'presenti, enabled, active')
  self.api('GET','/health',{'200'});self.api('GET','/status',{'200'})
  # Unauthorized must fail
  x=self.ssh(f"curl -s -o /dev/null -w '%{{http_code}}' http://127.0.0.1:{e['AGENT_PORT']}/status");self.out('PASS' if x.stdout.strip()=='401' else 'FAIL','Autenticazione agent',f"HTTP {x.stdout.strip()}")
  self.api('POST','/wakelock',{'200'});_,b=self.api('GET','/status',{'200'});self.out('PASS' if 'manual_wakelock' in b else 'FAIL','Policy wakelock','blocker verificato' if 'manual_wakelock' in b else b)
  self.api('DELETE','/wakelock',{'200'});self.api('POST','/activity/llm',{'202'});_,b=self.api('GET','/status',{'200'});self.out('PASS' if 'llm_active' in b else 'FAIL','Policy LLM heartbeat','blocker verificato' if 'llm_active' in b else b)
  self.ssh('rm -f /run/workstation-power-agent/llm-active-until /run/workstation-power-agent/wakelock')
  vm=self.ssh(f"qm status {e['POWER_GAMING_VMID']}; qm status {e['POWER_LLM_VMID']}");self.out('PASS' if vm.returncode==0 else 'FAIL','Comandi qm',vm.stdout.strip() or vm.stderr.strip())
  if e.get('POWER_CYCLE_TEST','false').lower()!='true':self.out('FAIL','Power-cycle','impostare POWER_CYCLE_TEST=true nel .env per autorizzare shutdown e secondo WoL');return
  _,b=self.api('POST','/shutdown',{'202'})
  if 'accepted' not in b or 'true' not in b.lower():self.out('FAIL','Shutdown request',b);return
  if not self.wait(False,int(e['POWER_SHUTDOWN_TIMEOUT'])):self.out('FAIL','Spegnimento host','host ancora raggiungibile');return
  self.out('PASS','Spegnimento host','SSH offline')
  self.wol();self.out('PASS','Secondo Wake-on-LAN','Magic Packet inviato dopo poweroff')
  if not self.wait(True,int(e['POWER_BOOT_TIMEOUT'])):self.out('FAIL','Riaccensione finale','timeout');return
  r=self.ssh('systemctl is-active --quiet workstation-power-agent');self.out('PASS' if r.returncode==0 else 'FAIL','Riaccensione finale','agent active' if r.returncode==0 else r.stderr.strip())

def main():
 p=argparse.ArgumentParser(description='Diagnostica end-to-end distruttiva');p.add_argument('--env-file',default='router/.env');a=p.parse_args();e=load(a.env_file);print('Workstation Powersaver full diagnostic\n');d=D(e);d.go();print(f'\nOutcome: {"TUTTE LE FUNZIONI VERIFICATE" if not d.fail else str(d.fail)+" FUNZIONI FALLITE"}');raise SystemExit(bool(d.fail))
if __name__=='__main__':main()
