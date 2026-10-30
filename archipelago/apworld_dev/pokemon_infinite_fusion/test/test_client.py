import unittest

from .. import client


class TestRoomMessages(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.ctx = client.PokemonIFContext(None, None)
        self.ctx.slot = 1

    async def asyncTearDown(self):
        await self.ctx.shutdown()
        while not client.game_receive_queue.empty():
            client.game_receive_queue.get()

    def send(self, **args):
        self.ctx.on_package("PrintJSON", {"data": [{"text": "hola"}], **args})
        return client.game_receive_queue.qsize()

    async def test_only_own_items_reach_the_game(self):
        self.assertEqual(self.send(type="ItemSend", receiving=2), 0)
        self.assertEqual(self.send(type="Chat"), 0)
        self.assertEqual(self.send(type="ItemSend", receiving=1), 1)
