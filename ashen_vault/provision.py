"""Operator-only local provisioning. Never prints identity tokens or overwrites a key file."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
from agent_world import WorldRuntime
from agent_world.world_sdk import install_world
from .world import WORLD


def provision(db: Path, output: Path, name: str, *, campaign: bool = False) -> str:
    # Reserve output before allocating a role, so an existing key cannot be lost.
    output.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        world,universe=WORLD,'ashen-vault'
        if campaign:
            from .campaign_world import WORLD as story_world,UNIVERSE
            world,universe=story_world,UNIVERSE
        runtime=WorldRuntime(db);install_world(runtime,universe,world)
        role=runtime.create_role(name)
        token=runtime.issue_identity_token(universe,role['role_id'])
        with os.fdopen(fd,'w',encoding='utf-8') as stream:
            fd=None
            json.dump({'world':universe,'role_id':role['role_id'],'identity_token':token['token'],
                       'notice':'User-held role key. Anyone holding it can control this role. Keep privately; no automatic recovery.'},stream,ensure_ascii=False,indent=2)
        return role['role_id']
    finally:
        if fd is not None:os.close(fd)


def main():
    parser=argparse.ArgumentParser(description='Write a new user-held Ashen Vault key to a private file, without printing it.')
    parser.add_argument('--db',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--name',required=True)
    parser.add_argument('--campaign',action='store_true')
    args=parser.parse_args()
    provision(args.db,args.out,args.name,campaign=args.campaign)
    print('Private identity file created. Save it securely and give it only to a trusted Agent. No key was printed.')


if __name__=='__main__':main()
