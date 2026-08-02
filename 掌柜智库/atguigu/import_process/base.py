"""
实现抽象基类
"""
from abc import ABC, abstractmethod
from atguigu.tool.logger import logger

class NodeBase(ABC):
    #定义类属性name,在初始化方法中强制子类必须重写name属性
    name = "node_base"
    def __init__(self):
        if self.name == "node_base":
            raise Exception(f"子类{self.__class__.__name__}必须重写父类的name属性")

    #定义抽象方法,所有子类必须重写该方法
    @abstractmethod
    def process(self,state):
        pass

    #定义__call__方法,所有子类()调用时自动触发__call__方法
    def __call__(self, state):
        try:
            logger.info(f"节点{self.name}开始执行了")
            result = self.process(state)
            logger.info(f"节点{self.name}执行结束了")
            return result
        except Exception as e:
            logger.error(f"节点{self.name}执行异常了")
            raise e

