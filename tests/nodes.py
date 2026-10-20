"""Nodes like the bridge announces them, for the tests that set up the integration."""

from aiocomfoconnect.bridge import Node
from aiocomfoconnect.const import ProductId

UNIT = Node(1, ProductId.COMFOAIRQ, 1, 2)
LAN_C = Node(48, ProductId.ZEHNDERGATEWAY, 255, 2)


def announcing(*nodes: Node):
    """Return a connect() to patch with autospec, that announces these nodes like the bridge does when a session starts."""

    async def connect(bridge, uuid):
        bridge._nodes.update({node.node_id: node for node in nodes})

    return connect
