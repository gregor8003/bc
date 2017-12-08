from unittest import TestCase
import asyncio

from aiohttp.test_utils import unittest_run_loop, TestClient, setup_test_loop,\
    teardown_test_loop

from app import BlockchainApp
from blockchain import Blockchain, BlockMismatchException


class BlockchainTestCase(TestCase):

    def setUp(self):
        self.blockchain = Blockchain()

    def test_mine_single_block(self):
        # GIVEN
        lastBlock, _ = self.blockchain.getLatestBlock()
        self.assertEquals(lastBlock, self.blockchain.getGenesisBlock())
        # WHEN
        data = 'New block #2'
        newBlock = self.blockchain.generateNextBlock(data)
        self.blockchain.addBlock(newBlock)
        # THEN
        lastBlock, _ = self.blockchain.getLatestBlock()
        self.assertEquals(lastBlock, newBlock)

    def test_mine_three_blocks(self):
        # GIVEN
        lastBlock, _ = self.blockchain.getLatestBlock()
        self.assertEquals(lastBlock, self.blockchain.getGenesisBlock())
        # WHEN
        blocks = []
        for i in range(1, 4):
            data = 'New block #{}'.format(i)
            newBlock = self.blockchain.generateNextBlock(data)
            self.blockchain.addBlock(newBlock)
            blocks.append(newBlock)
        # THEN
        lastBlock, _ = self.blockchain.getLatestBlock()
        self.assertEquals(lastBlock, blocks[-1])

    def test_mine_invalid_block(self):
        # GIVEN
        lastBlock, _ = self.blockchain.getLatestBlock()
        self.assertEquals(lastBlock, self.blockchain.getGenesisBlock())
        # WHEN
        data = 'New block #2'
        newBlock = self.blockchain.generateNextBlock(data)
        # introduce discrepancy
        newBlock.index = -1
        newBlock.timestamp = self.blockchain.getTimestamp() - 1000
        # THEN
        with self.assertRaises(BlockMismatchException):
            self.blockchain.addBlock(newBlock)


class BlockchainAppTestMixin:

    async def pause(self):
        # add minimal sleep to advance loop tasks
        await asyncio.sleep(0.125, loop=self.loop)

    def setup_node(self, http_port, ws_port):
        bapp = BlockchainApp(
            loop=self.loop, http_port=http_port, ws_port=ws_port
        )
        bapp.setup()
        client = TestClient(bapp.app, loop=self.loop)
        self.loop.run_until_complete(client.start_server())
        bapp.http_port = client.port
        return (bapp, client)

    def teardown_node(self, client):
        self.loop.run_until_complete(client.close())

    def setup_loop(self):
        self.loop = setup_test_loop()

    def teardown_loop(self):
        teardown_test_loop(self.loop)

    async def add_as_peers(self, peers_info):
        for src, dst in peers_info.items():
            client = self.clients[src]
            resp = await client.request(
                'POST', '/addPeer', data={'peer': '127.0.0.1:{}'.format(dst)}
            )
            assert resp.status == 200
            assert await resp.text() == 'OK'

    def assertAreTheSame(self, sequence, message_predicate):
        el0 = sequence[0]
        for el in sequence:
            self.assertEqual(el0, el, message_predicate(el0, el))


class ABlockchainAppPeersTestCase(BlockchainAppTestMixin, TestCase):

    HTTP_PORTS = ['5001', '5002']
    WS_PORTS = ['3001', '3002']
    PEERS = {
        '3001': '3002',
        '3002': '3001',
    }

    def setUp(self):
        self.setup_loop()
        self.bapps = {}
        self.clients = {}
        for http_port, ws_port in zip(self.HTTP_PORTS, self.WS_PORTS):
            bapp, client = self.setup_node(
                http_port=http_port, ws_port=ws_port
            )
            self.bapps[http_port] = bapp
            self.clients[ws_port] = client

    def tearDown(self):
        for client in self.clients.values():
            self.teardown_node(client)
        self.teardown_loop()

    @unittest_run_loop
    async def test_add_as_peers(self):
        # GIVEN & WHEN
        for src, dst in self.PEERS.items():
            client = self.clients[src]
            resp = await client.request(
                'POST', '/addPeer', data={'peer': '127.0.0.1:{}'.format(dst)}
            )
            # THEN
            self.assertEqual(resp.status, 200)
            self.assertEqual(await resp.text(), 'OK')
            await self.pause()
            resp_peers = await client.request('GET', '/peers')
            self.assertEqual(resp_peers.status, 200)
            expected_peers = ['127.0.0.1:{}'.format(dst)]
            self.assertEqual(await resp_peers.json(), expected_peers)


class BBlockchainAppMinesTestCase(BlockchainAppTestMixin, TestCase):

    HTTP_PORTS = ['5001', '5002']
    WS_PORTS = ['3001', '3002']
    PEERS = {
        '3001': '3002',
        '3002': '3001',
    }

    def setUp(self):
        self.setup_loop()
        self.bapps = {}
        self.clients = {}
        for http_port, ws_port in zip(self.HTTP_PORTS, self.WS_PORTS):
            bapp, client = self.setup_node(
                http_port=http_port, ws_port=ws_port
            )
            self.bapps[http_port] = bapp
            self.clients[ws_port] = client
        self.loop.run_until_complete(self.add_as_peers(self.PEERS))

    def tearDown(self):
        for client in self.clients.values():
            self.teardown_node(client)
        self.teardown_loop()

#     @unittest_run_loop
#     async def test_mine_single_block(self):
#         # GIVEN
#         mine_client = self.clients[self.WS_PORTS[0]]
#         # WHEN
#         resp_mine = await mine_client.request(
#             'POST', '/mineBlock', data={'data': 'New block #2'}
#         )
#         self.assertEqual(resp_mine.status, 200)
#         self.assertEqual(await resp_mine.text(), 'OK')
#         await self.pause()
#         # THEN
#         lastBlocks = []
#         for src in self.HTTP_PORTS:
#             last, _ = self.bapps[src].blockchain.getLatestBlock()
#             lastBlocks.append(last)
#         self.assertAreTheSame(
#             lastBlocks, lambda a, b: '{} != {}'.format(
#                 a.jsonify(), b.jsonify()
#             )
#         )

    @unittest_run_loop
    async def test_mine_three_blocks(self):
        # GIVEN
        mine_client = self.clients[self.WS_PORTS[0]]
        # WHEN
        resp_mine = []
        for i in range(1, 4):
            resp_mine.append(await mine_client.request(
                'POST', '/mineBlock', data={'data': 'New block #{}'.format(i)}
            ))
        for r in resp_mine:
            self.assertEqual(r.status, 200)
            self.assertEqual(await r.text(), 'OK')
        await self.pause()
        # THEN
        lastBlocks = []
        for src in self.HTTP_PORTS:
            last, _ = self.bapps[src].blockchain.getLatestBlock()
            lastBlocks.append(last)
        self.assertAreTheSame(
            lastBlocks, lambda a, b: '{} != {}'.format(
                a.jsonify(), b.jsonify()
            )
        )


class CBlockchainAppReplaceChainTestCase(BlockchainAppTestMixin, TestCase):

    HTTP_PORTS = ['5001', '5002']
    NEW_HTTP_PORT = '5003'
    WS_PORTS = ['3001', '3002']
    NEW_WS_PORT = '3003'
    PEERS = {
        '3001': '3002',
        '3002': '3001',
    }
    NEW_PEERS = {
        '3003': '3001',
    }

    async def mine_some_blocks(self, count):
        mine_client = self.clients[self.WS_PORTS[0]]
        resp_mine = []
        for i in range(1, count+1):
            resp_mine.append(await mine_client.request(
                'POST', '/mineBlock', data={'data': 'New block #{}'.format(i)}
            ))
        for r in resp_mine:
            assert r.status == 200
            assert await r.text() == 'OK'

    def setUp(self):
        self.setup_loop()
        self.bapps = {}
        self.clients = {}
        for http_port, ws_port in zip(self.HTTP_PORTS, self.WS_PORTS):
            bapp, client = self.setup_node(
                http_port=http_port, ws_port=ws_port
            )
            self.bapps[http_port] = bapp
            self.clients[ws_port] = client
        self.loop.run_until_complete(self.add_as_peers(self.PEERS))
        #####
        self.loop.run_until_complete(self.mine_some_blocks(4))
        #####
        new_bapp, new_client = self.setup_node(
            self.NEW_HTTP_PORT, self.NEW_WS_PORT
        )
        self.bapps[self.NEW_HTTP_PORT] = new_bapp
        self.clients[self.NEW_WS_PORT] = new_client

    def tearDown(self):
        for client in self.clients.values():
            self.teardown_node(client)
        self.teardown_loop()

    @unittest_run_loop
    async def test_added_new_peer(self):
        # GIVEN & WHEN
        await self.add_as_peers(self.NEW_PEERS)
        # THEN
        await self.pause()
        new_client = self.clients[self.NEW_WS_PORT]
        resp_peers = await new_client.request('GET', '/peers')
        self.assertEqual(resp_peers.status, 200)
        expected_peers = ['127.0.0.1:{}'.format(self.WS_PORTS[0])]
        self.assertEqual(await resp_peers.json(), expected_peers)
        await self.pause()
        lastBlock, _ = (
            self.bapps[self.HTTP_PORTS[0]].blockchain.getLatestBlock()
        )
        newLastBlock, _ = (
            self.bapps[self.NEW_HTTP_PORT].blockchain.getLatestBlock()
        )
        self.assertEqual(newLastBlock, lastBlock, '{} != {}'.format(
                newLastBlock.jsonify(), lastBlock.jsonify()
            )
        )
