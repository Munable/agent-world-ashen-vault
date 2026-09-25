"""Thin HTTP/MCP composition; no account service or provider orchestration."""
from __future__ import annotations
import argparse
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit
from fastapi.responses import FileResponse, PlainTextResponse
from starlette.applications import Starlette
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.routing import Mount
from agent_world.http_app import create_app as http_app
from agent_world.mcp_app import create_mcp_app
from agent_world.world_sdk import install_world
from .world import WORLD


def create_app(db, origin='http://127.0.0.1:8850', *, campaign=False):
    if not isinstance(origin, str) or any(c.isspace() or ord(c) < 32 for c in origin) or '\\' in origin:
        raise ValueError('invalid origin')
    parsed = urlsplit(origin)
    if (parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username is not None or parsed.password is not None
            or parsed.path not in ('', '/') or parsed.query or parsed.fragment):
        raise ValueError('origin must be a credential-free HTTP origin')
    _ = parsed.port
    if parsed.scheme == 'http' and parsed.hostname not in ('127.0.0.1', 'localhost', '::1'):
        raise ValueError('non-loopback origins require HTTPS')
    origin = origin.rstrip('/')
    world, universe = WORLD, 'ashen-vault'
    if campaign:
        from .campaign_world import WORLD as story_world, UNIVERSE
        world, universe = story_world, UNIVERSE
    installer = lambda runtime, universe: install_world(runtime, universe, world)
    mcp, _, runtime = create_mcp_app(db, universe, auth_required=True, installer=installer, host=parsed.hostname)
    api = http_app(db, universe, auth_required=True, installer=installer)
    web = Path(__file__).parent/'web'

    @api.get('/agent', response_class=PlainTextResponse)
    def guide():
        if campaign:
            return ('Ashen Vault G2 Phase A preview. Use the user-held token for ashen-vault-ember, never create a substitute identity.\n'
                    f'GET {origin}/v1/whoami then {origin}/v1/bootstrap. Discover prefix=adventure. and inspect current schemas.\n'
                    'POST /v1/functions/<tool>/invoke with operation_id and arguments for writes; omit operation_id for look.\n'
                    'Read adventure.look. On first join choose one offered Fighter/Rogue/Wizard build; an existing campaign keeps its original class. Use offered actions and the current revision/turn_id. React only to your pending window. party.* is a separate shared combat/rest preview, not the six-region co-op campaign.\n'
                    'Missing credentials: stop. Unsupported actions: report the limit. NPCs are script-driven, not external Agents.\n'
                    'Never supply rolls/damage/rewards or assume resumed success from merely reading this guide.\n'
                    'Use SAME operation_id and args after an uncertain response. View /v1/receipts/<id> to verify.\n'
                    'Do not disclose token or Authorization. Report verified progress and whether the turn stopped. No background-play claim.\n')
        return f"""Ashen Vault M1 / SRD 5.2.1 bounded melee rules laboratory.
Not a complete D&D game: no PC classes, spells, ranged attacks, or arbitrary DM decisions yet.
The identity token belongs to the user. Use their token, not a new identity or a guessed one.
Authenticate each request: Authorization: Bearer <user identity token>. Never publish the token.
GET {origin}/v1/whoami, then GET {origin}/v1/bootstrap. Inspect your seat and the scene.
GET {origin}/v1/discover?prefix=vault.&include_schemas=true before actions.
HTTP invokes POST {origin}/v1/functions/<function>/invoke with
{{"operation_id":"<unique intent>","arguments":{{}}}}; fill arguments from that function schema.
Read vault.look omits operation_id. Join exactly one open seat using your own token.
The two seats are NPC melee rule fixtures, not level-3 Fighter/Rogue/Wizard characters.
Both users join independently; vault.begin starts a combat once. The server rolls all dice.
Use the observed turn_id for ordinary actions. A pending reaction pauses movement BEFORE leaving reach.
Only its reactor may call vault.react with window_id, even off turn; others must wait.
An awaiting_reaction receipt is not arrival. Read the scene after a reaction resolves.
No timeout auto-pass: disconnected users resume with the same key. A combat round is fictional time, not a wall-clock deadline.
For uncertain writes, GET {origin}/v1/receipts/<operation_id>; retry the SAME operation_id and arguments.
Never invent rolls, damage or success. Unsupported rules are unavailable, not approximate successes.
Report only actual outcomes in the user's language; do not repeat token/Authorization or claim background play.
"""

    @api.get('/watch')
    @api.get('/')
    def watch():
        return FileResponse(web/('campaign.html' if campaign else 'index.html'))

    @api.get('/watch.js')
    def javascript():
        return FileResponse(web/'watch.js', media_type='text/javascript')

    @api.get('/campaign.js')
    def campaign_script():return FileResponse(web/'campaign.js',media_type='text/javascript')

    @api.get('/campaign-player.js')
    def campaign_player():return FileResponse(web/'campaign-player.mjs',media_type='text/javascript')

    @api.get('/campaign-assets.json')
    def campaign_assets():return FileResponse(web/'campaign-assets.json',media_type='application/json')

    class Dispatch:
        async def __call__(self, scope, receive, send):
            target = mcp if scope.get('path', '').rstrip('/') == '/mcp' else api
            await target(scope, receive, send)

    @asynccontextmanager
    async def lifespan(app):
        async with mcp.app.router.lifespan_context(mcp.app):
            yield

    app = Starlette(routes=[Mount('/', app=Dispatch())], lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[parsed.hostname, '127.0.0.1', 'localhost', 'testserver'])
    app.state.runtime = runtime
    return app


def main():
    parser = argparse.ArgumentParser(description='Run the isolated Ashen Vault M1 laboratory.')
    parser.add_argument('--db', default='private/ashen-vault.sqlite3')
    parser.add_argument('--port', type=int, default=8850)
    parser.add_argument('--campaign', action='store_true', help='Run the private G2 preview instead of the M1 laboratory')
    args = parser.parse_args()
    import uvicorn
    uvicorn.run(create_app(args.db, f'http://127.0.0.1:{args.port}',campaign=args.campaign), host='127.0.0.1', port=args.port, log_level='warning')


if __name__ == '__main__':
    main()
