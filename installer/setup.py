#!/usr/bin/env python3
import argparse,os,secrets,shutil,socket,subprocess,sys,tarfile,tempfile,time,urllib.parse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'));from envfile import load,update

def run(c,**k):return subprocess.run(c,check=k.pop('check',True),text=True,**k)
def wol(mac,b,p):
 x=bytes.fromhex('FF'*6+mac.replace(':','').replace('-','')*16)
 with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as s:s.setsockopt(socket.SOL_SOCKET,socket.SO_BROADCAST,1);s.sendto(x,(b,p))
def ssh(e,c,check=True,timeout=20):return run(['ssh','-p',e['POWER_SSH_PORT'],'-o','BatchMode=yes','-o','ConnectTimeout=5','-o','StrictHostKeyChecking=accept-new',f"{e['POWER_SSH_USER']}@{e['POWER_HOST']}",c],check=check,capture_output=True,timeout=timeout)
def ready(e):return ssh(e,'true',False).returncode==0
def remote_script(port):return f'''#!/bin/bash
set -euo pipefail
A=$1;R=$2;B=/opt/workstation-power-agent;D=$B/releases/$R;C=$B/current;P="";[ ! -L "$C" ]||P=$(readlink -f "$C")
rollback(){{ systemctl stop workstation-power-agent||true;if [ -n "$P" ];then ln -sfn "$P" "$C";systemctl restart workstation-power-agent||true;else rm -f "$C";fi;rm -rf "$D"; }};trap rollback ERR
mkdir -p "$D/bin" /etc/workstation-power-agent;tar -xzf "$A" -C "$D";install -m600 "$D/config.toml" /etc/workstation-power-agent/config.toml;install -m600 "$D/token" /etc/workstation-power-agent/token;install -m644 "$D/service" /etc/systemd/system/workstation-power-agent.service
printf '#!/bin/bash\nHERE=$(cd "$(dirname "$0")/.." && pwd);export PYTHONPATH="$HERE/src";exec python3 -m workstation_power_agent.main "$@"\n' >"$D/bin/workstation-power-agent";chmod +x "$D/bin/workstation-power-agent";ln -sfn "$D" "$C";systemctl daemon-reload;systemctl enable --now workstation-power-agent
for i in $(seq 1 30);do curl -fsS http://127.0.0.1:{port}/health&&trap - ERR&&exit 0;sleep 1;done;exit 1
'''
def main():
 p=argparse.ArgumentParser();p.add_argument('--env-file',default='router/.env');p.add_argument('--enable-poweroff',action='store_true');a=p.parse_args();e=load(a.env_file)
 host=e.get('POWER_HOST') or urllib.parse.urlparse(e['PROXMOX_BASE_URL']).hostname; token=e.get('AGENT_TOKEN') or secrets.token_urlsafe(32)
 changes={'POWER_HOST':host,'POWER_SSH_USER':e.get('POWER_SSH_USER','root'),'POWER_SSH_PORT':e.get('POWER_SSH_PORT','22'),'POWER_GAMING_VMID':e.get('POWER_GAMING_VMID','100'),'POWER_LLM_VMID':e.get('POWER_LLM_VMID',e.get('PROXMOX_VMID','101')),'AGENT_PORT':e.get('AGENT_PORT','8765'),'AGENT_TOKEN':token,'POWER_BOOT_TIMEOUT':e.get('POWER_BOOT_TIMEOUT','180'),'POWER_SHUTDOWN_TIMEOUT':e.get('POWER_SHUTDOWN_TIMEOUT','120')};update(a.env_file,changes);e.update(changes)
 if not ready(e):wol(e['GAMING_MAC'],e.get('GAMING_BROADCAST','255.255.255.255'),int(e.get('GAMING_WOL_PORT','9')));end=time.time()+int(e['POWER_BOOT_TIMEOUT']);
 else:end=0
 while end and time.time()<end and not ready(e):time.sleep(3)
 if not ready(e):raise SystemExit('SSH non disponibile dopo WoL')
 with tempfile.TemporaryDirectory() as z:
  d=Path(z);shutil.copytree(ROOT/'agent/src',d/'src');shutil.copy(ROOT/'agent/systemd/workstation-power-agent.service',d/'service');(d/'token').write_text(token);(d/'config.toml').write_text(f'''gaming_vmid = {e['POWER_GAMING_VMID']}\nllm_vmid = {e['POWER_LLM_VMID']}\ncheck_interval_seconds = 15\nllm_idle_timeout_seconds = 600\nshutdown_grace_seconds = 300\nobserve_only = {str(not a.enable_poweroff).lower()}\nlisten_host = "0.0.0.0"\nlisten_port = {e['AGENT_PORT']}\ntoken_file = "/etc/workstation-power-agent/token"\nstate_dir = "/run/workstation-power-agent"\n''');(d/'install').write_text(remote_script(e['AGENT_PORT']))
  arc=d/'bundle.tgz'
  with tarfile.open(arc,'w:gz') as t:
   for f in d.iterdir():
    if f!=arc:t.add(f,arcname=f.name)
  run(['scp','-P',e['POWER_SSH_PORT'],str(arc),f"{e['POWER_SSH_USER']}@{host}:/tmp/wpa.tgz"]);ssh(e,f'tar -xOf /tmp/wpa.tgz install >/tmp/wpa-install&&chmod +x /tmp/wpa-install&&/tmp/wpa-install /tmp/wpa.tgz {int(time.time())}',timeout=180)
 print(f'Installazione completata; configurazione aggiornata in {a.env_file}')
if __name__=='__main__':main()
