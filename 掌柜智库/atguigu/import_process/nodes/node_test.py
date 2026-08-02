

from atguigu.import_process.base import NodeBase
from atguigu.tool.logger import logger


class NodeTest(NodeBase):
    name = "node_test"
    def process(self,state):
        logger.info("测试节点执行中")
        return state


if __name__ == '__main__':
    node = NodeTest()
    init_state = {}
    result = node(init_state)
    logger.info(result)