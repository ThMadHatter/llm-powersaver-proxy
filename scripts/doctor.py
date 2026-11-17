#!/usr/bin/env python3
"""Single-command diagnostic checklist for Workstation Powersaver."""
from __future__ import annotations
import argparse, json, os, re, shutil, socket, subprocess, sys, urllib.error, urllib.request
from dataclasses import dataclass
from pathlib import Path

@dataclass
class Check:
    name: str
    status: str
    detail: str

class Doctor:
    def __init__(self, args): self.args=args; self.checks=[]; self.env={}
    def add(self,name,status,detail): self.checks.append(Check(name,status,detail)); print(f"[{status:4}] {name}: {detail}")
    def command(self,cmd,timeout=15): return subprocess.run(cmd,text=True,capture_output=True,timeout=timeout)
    def load_env(self):
        path=Path(self.args.env_file)
        if not path.exists(): return self.add("Router config","FAIL",f"file assente: {path}")
        for raw in path.read_text(encoding="utf-8").splitlines():
            line=raw.strip()
            if not line or line.startswith("#") or "=" not in line: continue
            key,value=line.split("=",1); self.env[key.strip()]=value.strip().strip('"').strip("'")
        required=("ROUTER_API_KEY","PROXMOX_BASE_URL","PROXMOX_NODE","PROXMOX_VMID","PROXMOX_TOKEN_ID","PROXMOX_TOKEN_SECRET","GAMING_MAC")
        missing=[k for k in required if not self.env.get(k)]
        self.add("Router config","FAIL" if missing else "PASS", "mancano: "+", ".join(missing) if missing else f"{path} valida, variabili essenziali presenti")
        mac=self.env.get("GAMING_MAC","")
        valid=bool(re.fullmatch(r"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}",mac))
        self.add("Wake-on-LAN config","PASS" if valid else "FAIL",f"MAC {mac or 'assente'}, broadcast {self.env.get('GAMING_BROADCAST','255.255.255.255')}, porta {self.env.get('GAMING_WOL_PORT','9')}")
    def local_service(self):
        if not shutil.which("systemctl"): return self.add("Router systemd","SKIP","systemctl non disponibile")
        r=self.command(["systemctl","is-active",self.args.router_service])
        self.add("Router systemd","PASS" if r.stdout.strip()=="active" else "FAIL",r.stdout.strip() or r.stderr.strip() or "inactive")
    def http(self,name,url,token=None,expected=(200,),warn_codes=()):
        headers={"Authorization":f"Bearer {token}"} if token else {}
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=5) as response:
                code=response.status; body=response.read(4096).decode(errors="replace")
        except urllib.error.HTTPError as exc: code=exc.code; body=exc.read(4096).decode(errors="replace")
        except Exception as exc: return self.add(name,"FAIL",str(exc))
        status="PASS" if code in expected else "WARN" if code in warn_codes else "FAIL"
        self.add(name,status,f"HTTP {code}: {body[:180]}")
    def local_router(self):
        port=self.env.get("LISTEN_PORT","8080"); base=self.args.router_url or f"http://127.0.0.1:{port}"
        self.http("Router liveness",base+"/health/live",expected=(200,))
        self.http("Router readiness",base+"/health/ready",expected=(200,),warn_codes=(503,))
    def ssh_base(self): return ["ssh","-p",str(self.args.ssh_port),"-o","BatchMode=yes","-o","ConnectTimeout=5","-o","StrictHostKeyChecking=accept-new",f"{self.args.ssh_user}@{self.args.host}"]
    def remote(self,command,timeout=20): return self.command(self.ssh_base()+[command],timeout)
    def remote_checks(self):
        if not self.args.host: return self.add("Remote agent","SKIP","specificare --host o DOCTOR_HOST")
        r=self.remote("true")
        if r.returncode: return self.add("SSH Proxmox","FAIL",r.stderr.strip() or "connessione fallita")
        self.add("SSH Proxmox","PASS",f"{self.args.ssh_user}@{self.args.host}:{self.args.ssh_port}")
        requirements=self.remote("python3 -c 'import sys; print(sys.version.split()[0])' && command -v qm systemctl curl tar >/dev/null")
        self.add("Prerequisiti Proxmox","PASS" if requirements.returncode==0 else "FAIL",requirements.stdout.strip() or requirements.stderr.strip())
        service=self.remote("systemctl is-enabled workstation-power-agent.service; systemctl is-active workstation-power-agent.service")
        lines=service.stdout.split()
        self.add("Agent systemd","PASS" if service.returncode==0 and "enabled" in lines and "active" in lines else "FAIL",service.stdout.strip() or service.stderr.strip())
        token_cmd="cat /etc/workstation-power-agent/token"
        token_result=self.remote(token_cmd)
        if token_result.returncode or len(token_result.stdout.strip())<32:
            return self.add("Agent token","FAIL","token remoto assente o non valido")
        token=token_result.stdout.strip(); self.add("Agent token","PASS",f"presente ({len(token)} caratteri)")
        port=self.args.agent_port
        health_cmd=f"curl -fsS --max-time 5 http://127.0.0.1:{port}/health"
        health=self.remote(health_cmd); self.add("Agent health","PASS" if health.returncode==0 else "FAIL",health.stdout.strip() or health.stderr.strip())
        auth_header=f"Authorization: Bearer {token}"
        status=self.remote(f"curl -fsS --max-time 5 -H {self.quote(auth_header)} http://127.0.0.1:{port}/status")
        if status.returncode: self.add("Agent status","FAIL",status.stderr.strip()); return
        try:
            payload=json.loads(status.stdout); state=payload["state"]
            detail=f"gaming={state['gaming_vm']}, llm={state['llm_vm']}, blocker={state['blocker']}, observe_only={payload['observe_only']}"
            code="WARN" if state["gaming_vm"]=="unknown" or state["llm_vm"]=="unknown" else "PASS"
            self.add("Agent status",code,detail)
        except Exception as exc: self.add("Agent status","FAIL",f"JSON non valido: {exc}")
        vmids=(self.args.gaming_vmid,self.args.llm_vmid)
        vm=self.remote("; ".join(f"qm status {v}" for v in vmids))
        self.add("VM Proxmox","PASS" if vm.returncode==0 else "FAIL",vm.stdout.strip() or vm.stderr.strip())
        bad=self.remote(f"curl -s -o /dev/null -w '%{{http_code}}' http://127.0.0.1:{port}/status")
        self.add("Agent authentication","PASS" if bad.stdout.strip()=="401" else "FAIL",f"senza token: HTTP {bad.stdout.strip()}")
    @staticmethod
    def quote(value):
        import shlex; return shlex.quote(value)
    def summary(self):
        counts={s:sum(c.status==s for c in self.checks) for s in ("PASS","WARN","FAIL","SKIP")}
        print(f"\nRisultato: {counts['PASS']} PASS, {counts['WARN']} WARN, {counts['FAIL']} FAIL, {counts['SKIP']} SKIP")
        if counts["FAIL"]: return 1
        if self.args.strict and (counts["WARN"] or counts["SKIP"]): return 2
        return 0

def parser():
    p=argparse.ArgumentParser(description="Checklist diagnostica Workstation Powersaver")
    p.add_argument("--env-file",default=os.getenv("DOCTOR_ENV_FILE","/opt/litellm-router/.env")); p.add_argument("--router-service",default="litellm-router.service")
    p.add_argument("--router-url",default=os.getenv("DOCTOR_ROUTER_URL")); p.add_argument("--host",default=os.getenv("DOCTOR_HOST")); p.add_argument("--ssh-user",default=os.getenv("DOCTOR_SSH_USER","root")); p.add_argument("--ssh-port",type=int,default=int(os.getenv("DOCTOR_SSH_PORT","22")))
    p.add_argument("--agent-port",type=int,default=int(os.getenv("DOCTOR_AGENT_PORT","8765"))); p.add_argument("--gaming-vmid",type=int,default=int(os.getenv("DOCTOR_GAMING_VMID","100"))); p.add_argument("--llm-vmid",type=int,default=int(os.getenv("DOCTOR_LLM_VMID","101"))); p.add_argument("--strict",action="store_true")
    return p

def main():
    d=Doctor(parser().parse_args()); print("Workstation Powersaver diagnostic\n")
    d.load_env(); d.local_service(); d.local_router(); d.remote_checks(); raise SystemExit(d.summary())
if __name__=="__main__": main()
