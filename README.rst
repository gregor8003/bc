Blockchain
==========

VERY IMPORTANT NOTE: You cannot use this to make any money. You have been warned ;)

This repository contains very quick and dirty (sort of) Python port of
Naivechain (https://github.com/lhartikk/naivechain). It illustrates bare
essentials of blockchain principle (block hashing, chaining,
peer-to-peer communication). Please see documentation there for details.

Built with:

* asyncio (https://docs.python.org/3/library/asyncio.html)
* aiohttp (https://github.com/aio-libs/aiohttp)
* websockets (https://pypi.python.org/pypi/websockets)


Usage
=====

Start some nodes with given HTTP_PORT and WS_PORT:

.. code-block:: bash

    $ python3 app.py 5001 3001
    $ python3 app.py 5002 3002
    $ python3 app.py 5003 3003

The node UI (http://localhost:HTTP_PORT) allows:

* listing all blocks
* listing all peers
* adding new peer
* mining new block 
