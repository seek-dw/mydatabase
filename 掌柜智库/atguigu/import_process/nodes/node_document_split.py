# atguigu/import_process/nodes/node_document_split.py
import json
import re
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter

from atguigu.import_process.base import NodeBase
from atguigu.import_process.state import ImportGraphState
from atguigu.tool.logger import logger
from atguigu.tool.convert_to_json import convert_to_json


class NodeDocumentSplit(NodeBase):
    """
    目的:将处理好图片的md文档进行切分成chunk
    一.拿到文档内容
        1.拿路径,拿标题,文件流拿文档
    二、切分文档内容后合并成按标题切分的区域块(粗切)
        1.统一换行符
        2.先按行大切分,正则匹配每行是代码块还是标题,通过切片合并成按标题划分的区域快,
        3.最后一个块
    三、使用递归分割器对每个区域快再次进行切分(精切)
        1.剥离每一区域的标题
        2.判断表格是否存在
        3.递归切割器切分并加入索引(溯源)
        4.将切分好的chunks文件流写入json文件备份
    """

    name = "node_document_split"

    def process(self, state: ImportGraphState):

        # 一.拿到文档内容
        md_path = state.get("md_path", "")
        if not md_path:
            logger.error("路径不存在")
            raise Exception("路径不存在")
        md_path_obj = Path(md_path)
        if not md_path_obj.exists():
            logger.error("路径不存在")
            raise Exception("路径不存在")

        file_title = state.get("file_title")
        if not file_title:
            #.stem去掉路径下最后一段的文件名的扩展名
            file_title = md_path_obj.stem

        with md_path_obj.open("r", encoding="utf-8") as f:
            md_content = f.read()
        # 二、切分文档内容后合并成按标题切分的区域块
        #1.统一换行符,所有的操作系统都支持\n换行
        md_content = md_content.replace("\r\n", "\n").replace("\r", "\n")

        #2.按行切分
        md_lines = md_content.split("\n")

        #3.正则匹配,markdown中代码块格式至少3个~或`
        code_pattern = r"(`{3,}|~{3,})"
        title_pattern = r"^\s*#{1,6}\s+.+"
        is_in_block = False
        marker = None
        current_idx = 0
        section_list=[]
        for idx , line in enumerate(md_lines):
            line = line.strip()
            #匹配到了代码块的符号
            if re.match(code_pattern, line):
                logger.info("匹配到了代码块")
                if not is_in_block:
                    logger.info("进入代码块")
                    is_in_block = True
                    marker = re.match(code_pattern, line).group(1)
                else:
                    if marker == re.match(code_pattern, line).group(1):
                        logger.info("退出代码块")
                        is_in_block = False
                        marker = None

            if not is_in_block and re.match(title_pattern,line):
                logger.info("匹配到了标题")
                #切片拿到该标题到上一个标题的前文
                temp_list = md_lines[current_idx:idx]
                content = "\n".join(temp_list)
                section_dict = {
                    "title":temp_list[0] if content.strip().startswith("#") else "自定义标题",
                    "content":content,
                    "file_title": file_title
                }
                section_list.append(section_dict)
                #重置idx,下次从这个idx开始切分
                current_idx = idx

            #按向前切片原则会漏掉最后一个标题的下文,拿到所有按标题切分的区域块
        section_list.append({
                "title":md_lines[current_idx],
                "content":"\n".join(md_lines[current_idx:]),
                "file_title": file_title
            })
        # 三、递归切割器
        spliter = RecursiveCharacterTextSplitter(
            separators = ["\n\n", "\n", "。", "！", "？", "；", ".", "!", "?", ";", " "],
            chunk_size = 300,
            chunk_overlap = 2
        )
        final_section_List= []
        for section in section_list:
            title = section.get("title")
            content = section.get("content")
            real_content = content[len(title):]if content.strip().startswith("#") else  content
            if len(real_content)<=300:
                final_section_List.append(
                    {
                        **section,
                        "part":0
                    }
                )
                continue
            if "<table" in real_content:
                final_section_List.append(
                    {
                        **section,
                        "part": 0
                    }
                )
                continue

            splite_chunk_list = spliter.split_text(real_content)
            for idx , splite_chunk in enumerate(splite_chunk_list):
                final_section_List.append(
                    {
                        "title": title,
                        "file_title":file_title,
                        "content":title +"\n\n"+ splite_chunk,
                        "part": idx
                    }
                )

        return final_section_List
if __name__ == '__main__':
    node = NodeDocumentSplit()
    init_state={
        "md_path": r"E:\AI大模型\第七阶段 掌柜智库\资料\05-设备手册汇总\doc\hak180产品安全手册\hak180产品安全手册_new.md"
    }
    res = node(init_state)
    logger.info(convert_to_json(res))