"""Isolated test server. Every test owns its temporary database and child process."""
from pathlib import Path
import os
import socket
import subprocess
import sys
import tempfile
import time
import httpx
from agent_world import WorldRuntime
from agent_world.world_sdk import install_world
from ashen_vault.world import WORLD

ROOT = Path(__file__).resolve().parents[1]


class LiveServer:
    def __init__(self, *, campaign=False):self.campaign=campaign

    def __enter__(self):
        self.tmp=tempfile.TemporaryDirectory(); self.db=Path(self.tmp.name)/'world.sqlite3'
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0)); self.port=sock.getsockname()[1]
        self.url=f'http://127.0.0.1:{self.port}'
        runtime=WorldRuntime(self.db);world,universe=WORLD,'ashen-vault'
        if self.campaign:
            from ashen_vault.campaign_world import WORLD as story,UNIVERSE
            world,universe=story,UNIVERSE
        install_world(runtime,universe,world)
        self.tokens={}
        for seat in (('hero',) if self.campaign else ('warden','sentinel')):
            role=runtime.create_role(seat)['role_id']
            self.tokens[seat]=runtime.issue_identity_token(universe,role)['token']
        self.log_path=Path(self.tmp.name)/'server.log';self.log=self.log_path.open('w',encoding='utf-8')
        self.proc=None
        try:self.start();return self
        except BaseException:self.__exit__();raise

    def start(self):
        self.proc=subprocess.Popen([sys.executable,'-u','-m','ashen_vault.server','--db',str(self.db),'--port',str(self.port),*(['--campaign'] if self.campaign else [])],
            cwd=ROOT,stdin=subprocess.DEVNULL,stdout=self.log,stderr=subprocess.STDOUT)
        deadline=time.monotonic()+60
        with httpx.Client(trust_env=False,timeout=.5) as client:
            while time.monotonic()<deadline:
                if self.proc.poll() is not None:raise RuntimeError(self.log_path.read_text(encoding='utf-8',errors='replace')[-2000:])
                try:
                    if client.get(self.url+'/health').status_code==200:return
                except httpx.HTTPError:pass
                time.sleep(.1)
        raise RuntimeError('Local test server did not become ready')

    def stop(self):
        if self.proc and self.proc.poll() is None:
            if os.name=='nt':subprocess.run(['taskkill','/PID',str(self.proc.pid),'/T','/F'],capture_output=True)
            else:self.proc.terminate()
            try:self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:self.proc.kill();self.proc.wait(timeout=5)

    def __exit__(self,*args):
        self.stop();self.log.close();self.tmp.cleanup()
