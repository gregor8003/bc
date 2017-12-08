
import itertools
import logging
import time

from Crypto.Hash import SHA256


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler())


def pairwise(iterable):
    "s -> (s0,s1), (s1,s2), (s2, s3), ..."
    a, b = itertools.tee(iterable)
    next(b, None)
    return zip(a, b)


class BlockMismatchException(Exception):
    pass


class Block:

    def __init__(self, index, previousHash, timestamp, data, hash_):
        self.index = index
        self.previousHash = previousHash
        self.timestamp = timestamp
        self.data = data
        self.hash = hash_

    def jsonify(self):
        return {
            'index': self.index,
            'previousHash': self.previousHash,
            'timestamp': self.timestamp,
            'data': self.data,
            'hash': self.hash,
        }

    @staticmethod
    def fromDict(dict_):
        return Block(
            index=dict_['index'],
            previousHash=dict_['previousHash'],
            timestamp=dict_['timestamp'],
            data=dict_['data'],
            hash_=dict_['hash']
        )

    def __eq__(self, other):
        return (
            self.index == other.index and
            self.previousHash == other.previousHash and
            self.timestamp == other.timestamp and
            self.data == other.data and
            self.hash == other.hash
        )


class Blockchain(object):

    def __init__(self):
        self.blockchain = list()
        self._make_genesis()

    def _make_genesis(self):
        genesis = self.getGenesisBlock()
        self.blockchain.append(genesis)

    def jsoninfy(self):
        return [b.jsonify() for b in self.blockchain]

    def getGenesisBlock(self):
        genesis = Block(
            index=0, previousHash='0', timestamp=1465154705,
            data='my genesis block!!',
            hash_=(
                '816534932c2b7154836da6afc367695e6337db8a921823784c'
                '14378abed4f7d7'
            )
        )
        return genesis

    def getLatestBlock(self):
        return (self.blockchain[-1], len(self.blockchain)-1)

    def getTimestamp(self):
        return int(round(time.time()))

    def generateNextBlock(self, blockdata):
        previousBlock, previousBlockIndex = self.getLatestBlock()
        previousHash = previousBlock.hash
        nextIndex = previousBlockIndex + 1
        nextTimestamp = self.getTimestamp()
        nextHash = self.calculateHash(
            nextIndex, previousHash, nextTimestamp, blockdata
        )
        newBlock = Block(
            index=nextIndex, previousHash=previousHash,
            timestamp=nextTimestamp, data=blockdata, hash_=nextHash
        )
        return newBlock

    def calculateHashForBlock(self, block):
        return self.calculateHash(
            index=block.index, previousHash=block.previousHash,
            timestamp=block.timestamp, data=block.data
        )

    def calculateHash(self, index, previousHash, timestamp, data):
        hash_ = SHA256.new()
        message = '{}{}{}{}'.format(index, previousHash, timestamp, data)
        hash_.update(message.encode('utf-8'))
        return hash_.hexdigest()

    def isValidNewBlock(self, newBlock, previousBlock):
        prevIndex = previousBlock.index + 1
        newIndex = newBlock.index
        if prevIndex != newIndex:
            raise BlockMismatchException(
                'Invalid index: {} != {}'.format(
                    prevIndex, newIndex
                )
            )
        prevHash = previousBlock.hash
        newPrevHash = newBlock.previousHash
        if prevHash != newPrevHash:
            raise BlockMismatchException(
                'Invalid previousHash: {} != {}'.format(
                    prevHash, newPrevHash
                )
            )
        newHash = self.calculateHashForBlock(newBlock)
        newNewHash = newBlock.hash
        if newHash != newNewHash:
            raise BlockMismatchException(
                'Invalid hash: {} != {}'.format(
                    newHash, newNewHash
                )
            )

    def addBlock(self, newBlock):
        self.isValidNewBlock(newBlock, self.getLatestBlock()[0])
        self.blockchain.append(newBlock)

    def replaceChain(self, newBlocks):
        if (
            self.isValidChain(newBlocks) and
            len(newBlocks) > len(self.blockchain)
        ):
            logger.info(
                'Received blockchain is valid. Replacing current blockchain '
                'with received blockchain.'
            )
            self.blockchain.clear()
            self.blockchain.extend(newBlocks)
            return True
        else:
            logger.error(
                'Received blockchain is invalid.'
            )
            return False

    def isValidChain(self, chainBlocks):
        if self.getGenesisBlock() != chainBlocks[0]:
            logger.error(
                'Genesis does not match'
            )
            return False
        for prevBlock, nextBlock in pairwise(chainBlocks):
            try:
                self.isValidNewBlock(nextBlock, prevBlock)
            except BlockMismatchException as e:
                logger.error(e)
                return False
        return True
