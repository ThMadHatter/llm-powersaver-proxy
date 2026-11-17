import argparse,hmac,json,subprocess,threading,time,tomllib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path

def qm(v):
 try:
  x=subprocess.run(['/usr/sbin/qm','status',str(v)],capture_output=True,text=True,check=True,timeout=10).stdout.split()[-1];return x if x in ('running','stopped') else 'unknown'
 except Exception:return 'unknown'
class State:
 def __init__(self,c):self.c=c;self.lock=threading.Lock();self.idle=0;self.data={}
 def evaluate(self,ignore_grace=False):
  d=Path(self.c['state_dir'])
  try:a=int((d/'llm-active-until').read_text())>int(time.time())
  except Exception:a=False
  g,l=qm(self.c['gaming_vmid']),qm(self.c['llm_vmid']);w=(d/'wakelock').exists()
  b='vm_state_unknown' if 'unknown' in (g,l) else 'gaming_vm_running' if g=='running' else 'llm_active' if a else 'manual_wakelock' if w else 'shutdown_grace' if self.idle<self.c['shutdown_grace_seconds'] and not ignore_grace else None
  self.idle=self.idle+self.c['check_interval_seconds'] if b in (None,'shutdown_grace') else 0
  with self.lock:self.data={'gaming_vm':g,'llm_vm':l,'llm_active':a,'wakelock':w,'idle_seconds':self.idle,'blocker':b}
  return b
 def loop(self):
  while True:
   b=self.evaluate()
   if b is None and not self.c['observe_only']:
    print('Shutdown policy satisfied: powering off host',flush=True)
    try:subprocess.run(['/usr/bin/systemctl','poweroff'],check=True,timeout=30)
    except Exception as x:print(f'Poweroff failed: {x}',flush=True)
   time.sleep(self.c['check_interval_seconds'])
class H(BaseHTTPRequestHandler):
 def out(self,n,b):
  x=json.dumps(b).encode();self.send_response(n);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(x)));self.end_headers();self.wfile.write(x)
 def auth(self):return hmac.compare_digest(self.headers.get('Authorization',''),f'Bearer {self.server.token}')
 def do_GET(self):
  if self.path=='/health':return self.out(200,{'status':'ok','version':'0.4.1'})
  if self.path=='/status' and self.auth():self.server.state.evaluate();return self.out(200,{'state':self.server.state.data,'observe_only':self.server.state.c['observe_only']})
  self.out(401 if self.path=='/status' else 404,{'detail':'unauthorized'})
 def do_POST(self):
  if not self.auth():return self.out(401,{'detail':'unauthorized'})
  s=self.server.state;d=Path(s.c['state_dir']);d.mkdir(parents=True,exist_ok=True)
  if self.path=='/activity/llm':u=int(time.time())+s.c['llm_idle_timeout_seconds'];(d/'llm-active-until').write_text(str(u));return self.out(202,{'active_until':u})
  if self.path=='/wakelock':(d/'wakelock').touch();return self.out(200,{'wakelock':True})
  if self.path=='/shutdown':
   b=s.evaluate(True)
   if b:return self.out(409,{'accepted':False,'blocker':b})
   self.out(202,{'accepted':True});threading.Thread(target=lambda:(time.sleep(1),subprocess.run(['/usr/bin/systemctl','poweroff'])),daemon=True).start();return
  self.out(404,{'detail':'not found'})
 def do_DELETE(self):
  if not self.auth():return self.out(401,{'detail':'unauthorized'})
  if self.path=='/wakelock':(Path(self.server.state.c['state_dir'])/'wakelock').unlink(missing_ok=True);return self.out(200,{'wakelock':False})
  self.out(404,{'detail':'not found'})
 def log_message(self,*a):pass
def main():
 p=argparse.ArgumentParser();p.add_argument('--config',default='/etc/workstation-power-agent/config.toml');a=p.parse_args()
 with open(a.config,'rb') as f:c=tomllib.load(f)
 t=Path(c['token_file']).read_text().strip();Path(c['state_dir']).mkdir(parents=True,exist_ok=True);s=State(c);threading.Thread(target=s.loop,daemon=True).start();x=ThreadingHTTPServer((c['listen_host'],c['listen_port']),H);x.state=s;x.token=t;x.serve_forever()
if __name__=='__main__':main()
