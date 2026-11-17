#!/usr/bin/env python3
import argparse,secrets,shutil,socket,subprocess,sys,tarfile,tempfile,time,urllib.parse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'));from envfile import load,update
def run(c,**k):return subprocess.run(c,check=k.pop('check',True),text=True,**k)
def ssh(e,c,check=True,timeout=20):return run(['ssh','-p',e['POWER_SSH_PORT'],'-o','BatchMode=yes','-o','ConnectTimeout=5','-o','StrictHostKeyChecking=accept-new',f"{e['POWER_SSH_USER']}@{e['POWER_HOST']}",c],check=check,capture_output=True,timeout=timeout)
def ready(e):return ssh(e,'true',False).returncode==0
def wol(e):
 x=bytes.fromhex('FF'*6+e['GAMING_MAC'].replace(':','')*16)
 with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as s:s.setsockopt(socket.SOL_SOCKET,socket.SO_BROADCAST,1);s.sendto(x,(e['GAMING_BROADCAST'],int(e.get('GAMING_WOL_PORT','9'))))
def remote(port):return f'''#!/bin/bash
set -euo pipefail
A=$1;R=$2;B=/opt/workstation-power-agent;D=$B/releases/$R;C=$B/current;P="";[ ! -L "$C" ]||P=$(readlink -f "$C")
rollback(){{ systemctl stop workstation-power-agent||true;if [ -n "$P" ];then ln -sfn "$P" "$C";systemctl restart workstation-power-agent||true;else rm -f "$C";fi;rm -rf "$D"; }};trap rollback ERR
mkdir -p "$D/bin" /etc/workstation-power-agent;tar -xzf "$A" -C "$D";install -m600 "$D/config.toml" /etc/workstation-power-agent/config.toml;install -m600 "$D/token" /etc/workstation-power-agent/token;install -m644 "$D/service" /etc/systemd/system/workstation-power-agent.service
printf '#!/bin/bash\nHERE=$(cd "$(dirname "$0")/.." && pwd);export PYTHONPATH="$HERE/src";exec python3 -m workstation_power_agent.main "$@"\n' >"$D/bin/workstation-power-agent";chmod +x "$D/bin/workstation-power-agent";ln -sfn "$D" "$C";systemctl daemon-reload;systemctl enable workstation-power-agent;systemctl restart workstation-power-agent
for i in $(seq 1 30);do curl -fsS http://127.0.0.1:{port}/health&&trap - ERR&&exit 0;sleep 1;done;exit 1'''
def main():
 p=argparse.ArgumentParser();p.add_argument('--env-file',default='router/.env');p.add_argument('--enable-poweroff',action='store_true');a=p.parse_args();e=load(a.env_file);print('[1/8] Lettura configurazione',flush=True)
 host=e.get('POWER_HOST') or urllib.parse.urlparse(e['PROXMOX_BASE_URL']).hostname;token=e.get('AGENT_TOKEN') or secrets.token_urlsafe(32);ch={'POWER_HOST':host,'POWER_SSH_USER':e.get('POWER_SSH_USER','root'),'POWER_SSH_PORT':e.get('POWER_SSH_PORT','22'),'POWER_GAMING_VMID':e.get('POWER_GAMING_VMID','100'),'POWER_LLM_VMID':e.get('POWER_LLM_VMID',e.get('PROXMOX_VMID','101')),'AGENT_PORT':e.get('AGENT_PORT','8765'),'AGENT_TOKEN':token,'AGENT_BASE_URL':e.get('AGENT_BASE_URL',f'http://{host}:8765'),'AGENT_HEARTBEAT_PATH':e.get('AGENT_HEARTBEAT_PATH','/activity/llm'),'AGENT_HEARTBEAT_INTERVAL':e.get('AGENT_HEARTBEAT_INTERVAL','60'),'AGENT_TIMEOUT':e.get('AGENT_TIMEOUT','5'),'POWER_BOOT_TIMEOUT':e.get('POWER_BOOT_TIMEOUT','180'),'POWER_SHUTDOWN_TIMEOUT':e.get('POWER_SHUTDOWN_TIMEOUT','120')};update(a.env_file,ch);e.update(ch);print(f'[2/8] Target SSH: {host}',flush=True)
 print('[3/8] Verifica SSH iniziale',flush=True)
 if not ready(e):print('[4/8] Invio WoL',flush=True);wol(e);end=time.time()+int(e['POWER_BOOT_TIMEOUT'])
 else:end=0;print('      SSH gia disponibile',flush=True)
 while end and time.time()<end and not ready(e):print(f'      attesa SSH: {int(end-time.time())}s',flush=True);time.sleep(3)
 if not ready(e):raise SystemExit('SSH non disponibile dopo WoL')
 print('[5/8] Preparazione bundle',flush=True)
 with tempfile.TemporaryDirectory() as z:
  d=Path(z);shutil.copytree(ROOT/'agent/src',d/'src',ignore=shutil.ignore_patterns('__pycache__','*.pyc'));shutil.copy(ROOT/'agent/systemd/workstation-power-agent.service',d/'service');(d/'token').write_text(token);(d/'config.toml').write_text(f'''gaming_vmid = {e['POWER_GAMING_VMID']}\nllm_vmid = {e['POWER_LLM_VMID']}\ncheck_interval_seconds = 15\nllm_idle_timeout_seconds = 600\nshutdown_grace_seconds = 300\nobserve_only = {str(not a.enable_poweroff).lower()}\nlisten_host = "0.0.0.0"\nlisten_port = {e['AGENT_PORT']}\ntoken_file = "/etc/workstation-power-agent/token"\nstate_dir = "/run/workstation-power-agent"\n''');(d/'install').write_text(remote(e['AGENT_PORT']));arc=d/'bundle.tgz'
  with tarfile.open(arc,'w:gz') as t:
   for f in d.iterdir():
    if f!=arc:t.add(f,arcname=f.name)
  print('[6/8] Trasferimento SCP',flush=True);run(['scp','-P',e['POWER_SSH_PORT'],str(arc),f"{e['POWER_SSH_USER']}@{host}:/tmp/wpa.tgz"],timeout=120);print('[7/8] Installazione remota',flush=True);r=ssh(e,f'tar -xOf /tmp/wpa.tgz install >/tmp/wpa-install&&chmod +x /tmp/wpa-install&&/tmp/wpa-install /tmp/wpa.tgz {int(time.time())}',timeout=180);print(r.stdout.strip(),flush=True)
 print('[8/8] Installazione completata',flush=True)
if __name__=='__main__':main()
