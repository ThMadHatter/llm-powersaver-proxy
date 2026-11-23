#!/usr/bin/env python3
import argparse,json,socket,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from envfile import load

def ssh(e,cmd,timeout=5):
 opts=["-o",f"UserKnownHostsFile={e.get('SSH_KNOWN_HOSTS','/root/.ssh/known_hosts')}","-o","StrictHostKeyChecking=yes","-o","IdentitiesOnly=yes","-i",e.get("SSH_IDENTITY","/root/.ssh/id_ed25519")]
 return subprocess.run(["ssh","-p",e.get("POWER_SSH_PORT","22"),"-o","BatchMode=yes","-o",f"ConnectTimeout={timeout}",*opts,f"{e.get('POWER_SSH_USER','root')}@{e['POWER_HOST']}",cmd],text=True,capture_output=True)
def online(e):return ssh(e,"true",3).returncode==0
def wol(e):
 m=e["GAMING_MAC"].replace(":","").replace("-","");p=bytes.fromhex("FF"*6+m*16);t=(e.get("GAMING_BROADCAST","255.255.255.255"),int(e.get("GAMING_WOL_PORT","9")))
 with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as s:s.setsockopt(socket.SOL_SOCKET,socket.SO_BROADCAST,1);s.sendto(p,t)
 print(f"WoL inviato a {e['GAMING_MAC']} via {t[0]}:{t[1]}",flush=True)
def vmstatus(e):
 vmid=e.get("POWER_GAMING_VMID","100");r=ssh(e,f"qm status {vmid}",8);return r.stdout.strip()
def up(e):
 vmid=e.get("POWER_GAMING_VMID","100")
 if "running" in vmstatus(e):print(f"PASS: VM {vmid} già running");return 0
 try:wol(e)
 except Exception:pass
 r=ssh(e,f"qm start {vmid}",20)
 if r.returncode!=0:
  print(f"FAIL: qm start {vmid}: {(r.stdout+r.stderr).strip()[:180]}",file=sys.stderr);return 1
 end=time.time()+int(e.get("POWER_BOOT_TIMEOUT","180"));n=0
 while time.time()<end:
  n+=1
  if "running" in vmstatus(e):print(f"PASS: VM {vmid} running ({n}s)");return 0
  time.sleep(5)
 print("FAIL: boot timeout",file=sys.stderr);return 1
def down(e):
 if not online(e):print("Workstation già offline");return 0
 h=f"Authorization: Bearer {e['AGENT_TOKEN']}";u=f"http://127.0.0.1:{e.get('AGENT_PORT','8765')}/shutdown";r=ssh(e,f"curl -sS -o /tmp/power-down.json -w '%{{http_code}}' -X POST -H '{h}' {u}");b=ssh(e,"cat /tmp/power-down.json 2>/dev/null||true").stdout.strip();c=r.stdout.strip()
 if c=="202":print(f"PASS: shutdown accettato: {b}");return 0
 if c=="409":print(f"STOP: shutdown bloccato: {json.loads(b).get('blocker','sconosciuto')}",file=sys.stderr);return 2
 print(f"FAIL: HTTP {c or '?'} {b or r.stderr}",file=sys.stderr);return 1
def main():
 p=argparse.ArgumentParser();p.add_argument("action",choices=("up","down"));p.add_argument("--env-file",default="router/.env");a=p.parse_args();e=load(a.env_file);missing=[k for k in ("POWER_HOST","GAMING_MAC","AGENT_TOKEN") if not e.get(k)]
 if missing:raise SystemExit("Variabili mancanti: "+", ".join(missing))
 raise SystemExit(up(e) if a.action=="up" else down(e))
if __name__=="__main__":main()
