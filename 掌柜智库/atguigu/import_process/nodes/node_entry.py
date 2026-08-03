"""
1.入口节点
"""
from pathlib import Path

# atguigu/import_process/nodes/node_entry.py
from atguigu.import_process.base import NodeBase
from atguigu.import_process.state import ImportGraphState
from atguigu.tool.logger import logger


class NodeEntry(NodeBase):
    """
    核心任务: 判断本地上传的文件是md格式还是pdf格式
            加一个防御性编程
    """

    name = "node_entry"
    def process(self, state: ImportGraphState,local_file_path = None):
        #防御性编程
        local_file_path = state.get("local_file_path","")
        #判断上传路径str是否为空
        if not local_file_path:
            logger.erroe("上传路径错误")
            raise Exception("该路径为空,请提供本地上传路径")
        #上传路径有了,判断该路径是否真实存在

        local_file_path_obj = Path(local_file_path)

        #exist()判断该目录地址是否存在
        if not local_file_path_obj.exists():
            logger.error("上传路径错误")
            raise Exception("该路径不存在,请提供正确路径")

        if not local_file_path_obj.is_file():
            logger.error("上传路径错误")
            raise Exception("该路径不是文件,请提供正确路径")

        #防御性编程完成
        #有了真实存在的路径,判断该路径下的文件是什么文件
        #拿到文件名和后缀
        file_title = local_file_path_obj.stem
        suffix = local_file_path_obj.suffix
        if suffix == ".md":
            return {
                "file_title":file_title,
                "is_md_read_enabled":True,
                "md_path":local_file_path
            }
        if suffix == ".pdf":
            return{
                "file_title":file_title,
                "is_pdf_read_enabled":True,
                "pdf_path":local_file_path
            }
        else:
            logger.error("文件格式错误")
            raise Exception("请上传正确的文件格式, '.md' or '.pdf'")




if __name__ == '__main__':
    node = NodeEntry()
    init_state = {
        "local_file_path":r"E:\AI大模型\第七阶段 掌柜智库\掌柜智库01\资料\05-设备手册汇总\doc\hak180产品安全手册.pdf"
    }
    res = node(init_state)
    logger.info(res)
    """
    测试成功,拿到了本地文件上传路径,文件名,文件类型
    """