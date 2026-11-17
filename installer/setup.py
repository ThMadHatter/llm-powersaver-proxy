#!/usr/bin/env python3
import argparse, os, re, secrets, socket, subprocess, tarfile, tempfile, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; REMOTE="/tmp/workstation-power-agent.tgz"
def mac(v):
 c=re.sub('[^0-9A-Fa-f]','',v)
 if len(c)!=12: raise argparse.ArgumentTypeError('MAC non valido')
 return ':'.join(c[i:i+2] for i in range(0,12,2)).upper()
def run(c,**k): return subprocess.run(c,check=k.pop('check',True),text=True,**k)
def sshcmd(a): return ['ssh','-p',str(a.ssh_port),'-o','BatchMode=yes','-o','ConnectTimeout=5','-o','StrictHostKeyChecking=accept-new',f'{a.ssh_user}@{a.host}']
def ssh(a,cmd,**k): return run(sshcmd(a)+[cmd],**k)
def ready(a): return ssh(a,'true',check=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
def wol(m,b,p):
 packet=bytes.fromhex('FF'*6+m.replace(':','')*16)
 with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as s: s.setsockopt(socket.SOL_SOCKET,socket.SO_BROADCAST,1); s.sendto(packet,(b,p))
def config(a): return f'''gaming_vmid = {a.gaming_vmid}\nllm_vmid = {a.llm_vmid}\ncheck_interval_seconds = 15\nllm_idle_timeout_seconds = 600\nshutdown_grace_seconds = 300\nobserve_only = {str(not a.enable_poweroff).lower()}\nlisten_host = "0.0.0.0"\nlisten_port = {a.agent_port}\ntoken_file = "/etc/workstation-power-agent/token"\nstate_dir = "/run/workstation-power-agent"\n'''
def install_script(port): return f'''#!/bin/bash
set -euo pipefail
A=$1; R=$2; B=/opt/workstation-power-agent; D=$B/releases/$R; C=$B/current; P=""
[ ! -L "$C" ] || P=$(readlink -f "$C")
rollback() {{ systemctl stop workstation-power-agent || true; if [ -n "$P" ]; then ln -sfn "$P" "$C"; systemctl restart workstation-power-agent || true; else rm -f "$C"; fi; rm -rf "$D"; }}
trap rollback ERR
python3 -c 'import sys; assert sys.version_info >= (3,11)'
mkdir -p "$D/bin" /etc/workstation-power-agent "$B/releases"; tar -xzf "$A" -C "$D"
install -m600 "$D/config.toml" /etc/workstation-power-agent/config.toml; install -m600 "$D/token" /etc/workstation-power-agent/token
install -m644 "$D/workstation-power-agent.service" /etc/systemd/system/workstation-power-agent.service
cat > "$D/bin/workstation-power-agent" <<'EOF'
#!/bin/bash
HERE=$(cd "$(dirname "$0")/.." && pwd); export PYTHONPATH="$HERE/src"; exec python3 -m workstation_power_agent.main "$@"
EOF
chmod +x "$D/bin/workstation-power-agent"; ln -sfn "$D" "$C"; systemctl daemon-reload; systemctl enable --now workstation-power-agent
for i in $(seq 1 20); do curl -fsS http://127.0.0.1:{port}/health && trap - ERR && rm -f "$A" && exit 0; sleep 1; done
exit 1
'''
def bundle(a,path,token,broken=False):
 import shutil
 with tempfile.TemporaryDirectory() as x:
  s=Path(x); (s/'src').mkdir(); shutil.copytree(ROOT/'agent/src/workstation_power_agent',s/'src/workstation_power_agent')
  shutil.copy(ROOT/'agent/systemd/workstation-power-agent.service',s/'workstation-power-agent.service')
  (s/'config.toml').write_text(config(a)); (s/'token').write_text(token); (s/'install.sh').write_text(install_script(1 if broken else a.agent_port))
  with tarfile.open(path,'w:gz') as t:
   for f in s.rglob('*'): t.add(f,arcname=f.relative_to(s),recursive=False)
def deploy(a,token,broken=False):
 with tempfile.TemporaryDirectory() as x:
  p=Path(x)/'a.tgz'; bundle(a,p,token,broken)
  run(['scp','-P',str(a.ssh_port),'-o','BatchMode=yes','-o','StrictHostKeyChecking=accept-new',str(p),f'{a.ssh_user}@{a.host}:{REMOTE}'])
  rel=time.strftime('%Y%m%d%H%M%S')+str(os.getpid()); ssh(a,f'tar -xOf {REMOTE} install.sh >/tmp/wpa-install.sh && chmod 700 /tmp/wpa-install.sh && /tmp/wpa-install.sh {REMOTE} {rel}',timeout=180)
def parser():
 p=argparse.ArgumentParser(); p.add_argument('--host',required=True); p.add_argument('--ssh-user',default='root'); p.add_argument('--ssh-port',type=int,default=22); p.add_argument('--mac',type=mac); p.add_argument('--broadcast',default='255.255.255.255'); p.add_argument('--wol-port',type=int,default=9); p.add_argument('--gaming-vmid',type=int,default=100); p.add_argument('--llm-vmid',type=int,default=101); p.add_argument('--agent-port',type=int,default=8765); p.add_argument('--ssh-timeout',type=int,default=180); p.add_argument('--enable-poweroff',action='store_true'); p.add_argument('--skip-wol',action='store_true'); p.add_argument('--yes',action='store_true'); return p
def main():
 a=parser().parse_args(); token=secrets.token_urlsafe(32)
 if not ready(a):
  if not a.skip_wol:
   if not a.mac: raise SystemExit('--mac richiesto per WoL')
   wol(a.mac,a.broadcast,a.wol_port)
  end=time.time()+a.ssh_timeout
  while time.time()<end and not ready(a): time.sleep(3)
  if not ready(a): raise SystemExit('SSH non disponibile')
 deploy(a,token); print('AGENT_TOKEN='+token)
if __name__=='__main__': main()
