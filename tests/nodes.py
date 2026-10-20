"""The nodes of a ComfoAir Q behind a LAN C, like the bridge announces them."""

from aiocomfoconnect.bridge import Node
from aiocomfoconnect.const import ProductId

UNIT = Node(1, ProductId.COMFOAIRQ, 1, 2)
LAN_C = Node(48, ProductId.ZEHNDERGATEWAY, 255, 2)
