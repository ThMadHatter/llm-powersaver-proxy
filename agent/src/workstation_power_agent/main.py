import argparse, hmac, json, subprocess, threading, time, tomllib
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

@dataclass
class Snapshot:
    gaming_vm: str = "unknown"
    llm_vm: str = "unknown"
    llm_active: bool = False
    wakelock: bool = False
    idle_seconds: int = 0
    blocker: str | None = "starting"

def qm(vmid):
    try:
        result=subprocess.run(["/usr/sbin/qm","status",str(vmid)],capture_output=True,text=True,check=True,timeout=10)
        value=result.stdout.strip().split()[-1]
        return value if value in {"running","stopped"} else "unknown"
    except Exception: return "unknown"

def active(path):
    try: return int(path.read_text().strip()) > int(time.time())
    except Exception: return False

def decide(s, grace):
    if "unknown" in {s.gaming_vm,s.llm_vm}: return "vm_state_unknown"
    if s.gaming_vm == "running": return "gaming_vm_running"
    if s.llm_active: return "llm_active"
    if s.wakelock: return "manual_wakelock"
    if s.idle_seconds < grace: return "shutdown_grace"
    return None

class State:
    def __init__(self,cfg): self.cfg=cfg; self.value=Snapshot(); self.lock=threading.Lock()
    def evaluate(self):
        d=Path(self.cfg["state_dir"])
        with self.lock: old=self.value.idle_seconds
        s=Snapshot(qm(self.cfg["gaming_vmid"]),qm(self.cfg["llm_vmid"]),active(d/"llm-active-until"),(d/"wakelock").exists(),old)
        blocker=decide(s,self.cfg["shutdown_grace_seconds"])
        s.idle_seconds=old+self.cfg["check_interval_seconds"] if blocker in {None,"shutdown_grace"} else 0
        s.blocker=decide(s,self.cfg["shutdown_grace_seconds"])
        with self.lock: self.value=s
        if s.blocker is None and not self.cfg["observe_only"]:
            subprocess.run(["/usr/bin/systemctl","poweroff"],check=True)
    def loop(self):
        while True: self.evaluate(); time.sleep(self.cfg["check_interval_seconds"])

class Handler(BaseHTTPRequestHandler):
    def answer(self,code,body):
        data=json.dumps(body).encode(); self.send_response(code); self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(data))); self.end_headers(); self.wfile.write(data)
    def auth(self): return hmac.compare_digest(self.headers.get("Authorization",""),f"Bearer {self.server.token}")
    def do_GET(self):
        if self.path=="/health": return self.answer(200,{"status":"ok","version":"0.3.0"})
        if self.path=="/status" and self.auth():
            with self.server.state.lock: value=asdict(self.server.state.value)
            return self.answer(200,{"state":value,"observe_only":self.server.state.cfg["observe_only"]})
        self.answer(401 if self.path=="/status" else 404,{"detail":"unauthorized" if self.path=="/status" else "not found"})
    def do_POST(self):
        if not self.auth(): return self.answer(401,{"detail":"unauthorized"})
        d=Path(self.server.state.cfg["state_dir"]); d.mkdir(parents=True,exist_ok=True)
        if self.path=="/activity/llm":
            until=int(time.time())+self.server.state.cfg["llm_idle_timeout_seconds"]; (d/"llm-active-until").write_text(str(until)); return self.answer(202,{"active_until":until})
        if self.path=="/wakelock": (d/"wakelock").touch(); return self.answer(200,{"wakelock":True})
        self.answer(404,{"detail":"not found"})
    def log_message(self,*args): pass

def main():
    p=argparse.ArgumentParser(); p.add_argument("--config",default="/etc/workstation-power-agent/config.toml"); a=p.parse_args()
    with open(a.config,"rb") as f: cfg=tomllib.load(f)
    token=Path(cfg["token_file"]).read_text().strip(); Path(cfg["state_dir"]).mkdir(parents=True,exist_ok=True)
    state=State(cfg); threading.Thread(target=state.loop,daemon=True).start()
    server=ThreadingHTTPServer((cfg["listen_host"],cfg["listen_port"]),Handler); server.state=state; server.token=token; server.serve_forever()
if __name__=="__main__": main()
