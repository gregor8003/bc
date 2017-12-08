import asyncio
import json
import logging
import sys

from aiohttp import web
import aiohttp_jinja2
import jinja2
import websockets

from blockchain import Blockchain, Block

DEBUG = False

QUERY_LATEST = 'QUERY_LATEST'
QUERY_ALL = 'QUERY_ALL'
RESPONSE_BLOCKCHAIN = 'RESPONSE_BLOCKCHAIN'

if DEBUG:
    logging.getLogger('asyncio').setLevel(logging.DEBUG)
    wslogger = logging.getLogger('websockets')
    wslogger.setLevel(logging.DEBUG)
    wslogger.addHandler(logging.StreamHandler())
    wsslogger = logging.getLogger('websockets.server')
    wsslogger.setLevel(logging.DEBUG)
    wsslogger.addHandler(logging.StreamHandler())

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler())

############################################################################


class HTTPHandler:

    def __init__(self, bapp):
        self.bapp = bapp

    @aiohttp_jinja2.template('index.html')
    async def handle_index(self, request):
        return {
            'host': '127.0.0.1',
            'port': self.bapp.http_port,
        }

    async def handle_blocks(self, request):
        return web.json_response(self.bapp.blockchain.jsoninfy())

    async def handle_peers(self, request):
        return web.json_response(
            [peer for peer in sorted(self.bapp.peers.keys())]
        )

    async def handle_addPeer(self, request):
        post = await request.post()
        if 'peer' in post:
            peer = post['peer']
            self.bapp.connectToPeers([peer])
            response = web.Response(text='OK')
        else:
            response = web.Response(text='No peer specified')
        return response

    async def handle_mineBlock(self, request):
        post = await request.post()
        if 'data' in post:
            data = post['data']
            newBlock = self.bapp.blockchain.generateNextBlock(data)
            self.bapp.blockchain.addBlock(newBlock)
            logger.info('Mined new block: %s', newBlock.jsonify())
            await self.bapp.broadcastMsg(self.bapp.msgResponseLatest())
            response = web.Response(text='OK')
        else:
            response = web.Response(text='No data specified')
        return response


############################################################################

class WSHandler:

    def __init__(self, bapp):
        self.bapp = bapp

    async def ws_server_handler(self, websocket, path):
        try:
            await self.bapp.processMessages(websocket)
        except Exception:
            websocket.close()

    async def ws_client_handler(self, peer):
        ws_url = 'ws://' + peer
        async with websockets.connect(
                ws_url, loop=self.bapp.loop) as websocket:
            # store peer websocket
            self.bapp.peers[peer] = websocket
            # initiate communication with peer
            await self.bapp.broadcastMsg(self.bapp.msgQueryChainLength())
            try:
                await self.bapp.processMessages(websocket)
            except Exception:
                websocket.close()


############################################################################

class BlockchainApp:

    def __init__(self, loop=None, debug=False, blockchain=None,
                 http_port=None, ws_port=None):
        if loop:
            self.loop = loop
        else:
            self.loop = asyncio.get_event_loop()
        if debug:
            self.loop.set_debug(True)
        if http_port:
            self.http_port = http_port
        else:
            self.http_port = '5001'
        if ws_port:
            self.ws_port = ws_port
        else:
            self.ws_port = '3001'
        self.app = web.Application(loop=self.loop)
        if blockchain:
            self.blockchain = blockchain
        else:
            self.blockchain = Blockchain()
        self.http_handler = HTTPHandler(bapp=self)
        self._buildRouter()
        self.ws_handler = WSHandler(bapp=self)
        self.peers = {}
        self.client_tasks = {}
        self.ws_server = None

    async def writeMsg(self, websocket, message):
        await websocket.send(json.dumps(message))

    async def broadcastMsg(self, message):
        for _, websocket in self.peers.items():
            await self.writeMsg(websocket, message)

    def msgQueryChainLength(self):
        return {
            'type': QUERY_LATEST,
        }

    def msgQueryAll(self):
        return {
            'type': QUERY_ALL,
        }

    def msgResponseLatest(self):
        return {
            'type': RESPONSE_BLOCKCHAIN,
            'data': json.dumps(
                [self.blockchain.getLatestBlock()[0].jsonify()]
            )
        }

    def msgResponseChain(self):
        return {
            'type': RESPONSE_BLOCKCHAIN,
            'data': json.dumps(self.blockchain.jsoninfy())
        }

    async def processMessages(self, websocket):
        while True:
            raw_message = await websocket.recv()
            message = json.loads(raw_message)
            mtype = message.get('type')
            if mtype == QUERY_LATEST:
                await self.writeMsg(websocket, self.msgResponseLatest())
            elif mtype == QUERY_ALL:
                await self.writeMsg(websocket, self.msgResponseChain())
            elif mtype == RESPONSE_BLOCKCHAIN:
                await self.processBlockchainResponse(message)
            logger.debug('Message processed: %s', message)

    async def processBlockchainResponse(self, message):
        raw_data = message.get('data')
        bdata = json.loads(raw_data)
        if bdata:
            receivedBlocks = sorted(bdata, key=lambda b: b['index'])
            latestBlockReceived = receivedBlocks[-1]
            latestBlockHeld = self.blockchain.getLatestBlock()[0].jsonify()
            if latestBlockReceived['index'] > latestBlockHeld['index']:
                logger.info(
                    'Blockchain possibly behind. We got: %s, peer got: %s',
                    latestBlockHeld['index'],
                    latestBlockReceived['index']
                )
                if (latestBlockHeld['hash'] ==
                        latestBlockReceived['previousHash']):
                    logger.info(
                        'We can append the received block to our chain.'
                    )
                    self.blockchain.addBlock(
                        Block.fromDict(latestBlockReceived)
                    )
                    await self.broadcastMsg(self.msgResponseLatest())
                elif len(receivedBlocks) == 1:
                    logger.info(
                        'We have to query the chain from our peer.'
                    )
                    await self.broadcastMsg(self.msgQueryAll())
                else:
                    logger.info(
                        'Received blockchain is longer than '
                        'current blockchain.'
                    )
                    replaced = self.blockchain.replaceChain(
                        [Block.fromDict(b) for b in receivedBlocks]
                    )
                    if replaced:
                        await self.broadcastMsg(self.msgResponseLatest())
            else:
                logger.info(
                    'Received blockchain is not longer than received '
                    'blockchain. Do nothing.'
                )

    def connectToPeers(self, newPeers):
        for newPeer in newPeers:
            self.client_tasks[newPeer] = self._buildWSClient(newPeer)

    def setup(self, initial_peers=None):
        aiohttp_jinja2.setup(self.app, loader=jinja2.FileSystemLoader('.'))
        self._buildWSServer()
        initialPeers = initial_peers.split(',') if initial_peers else []
        self.connectToPeers(initialPeers)
        self.app.on_cleanup.append(self._cleanup_ws_client_handlers)
        self.app.on_cleanup.append(self._cleanup_ws_server)

    def run(self):
        web.run_app(
            self.app, host='127.0.0.1', port=int(self.http_port),
            loop=self.loop
        )

    async def _cleanup_ws_server(self, app):
        self.ws_server.close()

    async def _cleanup_ws_client_handlers(self, app):
        for _, task in self.client_tasks.items():
            task.cancel()
            await task

    def _buildRouter(self):
        self.app.router.add_get('/', self.http_handler.handle_index)
        self.app.router.add_get('/blocks', self.http_handler.handle_blocks)
        self.app.router.add_get('/peers', self.http_handler.handle_peers)
        self.app.router.add_post('/addPeer', self.http_handler.handle_addPeer)
        self.app.router.add_post(
            '/mineBlock', self.http_handler.handle_mineBlock
        )

    def _buildWSServer(self):
        self.ws_server = websockets.serve(
            self.ws_handler.ws_server_handler, host='127.0.0.1',
            port=int(self.ws_port), loop=self.loop
        )
        self.loop.run_until_complete(self.ws_server)

    def _buildWSClient(self, peer):
        return self.loop.create_task(self.ws_handler.ws_client_handler(peer))


if __name__ == '__main__':
    try:
        http_port = sys.argv[1]
    except IndexError:
        http_port = '5001'
    try:
        ws_port = sys.argv[2]
    except IndexError:
        ws_port = '3001'
    try:
        initial_peers = sys.argv[3]
    except IndexError:
        initial_peers = []
    blockchainApp = BlockchainApp(http_port=http_port, ws_port=ws_port)
    blockchainApp.setup(initial_peers=initial_peers)
    blockchainApp.run()
