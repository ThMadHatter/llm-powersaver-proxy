import asyncio,logging,httpx
log=logging.getLogger('litellm-router.heartbeat')
class AgentHeartbeat:
 def __init__(self,client,url,token,interval):self.client=client;self.url=url;self.token=token;self.interval=interval;self.task=None
 async def run(self):
  while True:
   try:r=await self.client.post(self.url,headers={'Authorization':f'Bearer {self.token}'});r.raise_for_status()
   except asyncio.CancelledError:raise
   except httpx.HTTPError as x:log.warning('Heartbeat agent fallito: %s',x)
   await asyncio.sleep(self.interval)
 async def start(self):
  if self.url and self.token and self.task is None:self.task=asyncio.create_task(self.run());await asyncio.sleep(0)
 async def stop(self):
  if self.task:
   self.task.cancel()
   try:await self.task
   except asyncio.CancelledError:pass
   self.task=None
