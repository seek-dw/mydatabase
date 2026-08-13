import re
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter

from atguigu.import_process.base import NodeBase
from atguigu.import_process.state import ImportGraphState
from atguigu.tool.convert_to_json import convert_to_json
from atguigu.tool.logger import logger


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
        md_path = state.get("md_path","")
        if not md_path:
            logger.error("上传路径错误")
            raise Exception("上传路径错误")
        md_path_obj = Path(md_path)
        if not md_path_obj.exists():
            logger.error("上传路径不存在")
            raise Exception("上传路径不存在")

        file_title = state.get("file_title")
        if not file_title:
            file_title = md_path_obj.stem

        with open(md_path_obj,"r",encoding="utf-8") as f:
            md_content = f.read()
            if not md_content:
                logger.error('文件内容为空')
                raise Exception('文件内容为空')

        md_lines = md_content.split("\n")
        code_pattern = r"(^`{3,}|~{3,})"
        title_pattern = r"^\s*#{1,6}\s+.+"
        is_in_block = False
        marker = None
        current_idx = 0
        section_list = []
        for idx,line in enumerate(md_lines):
            line.strip()
            if re.match(code_pattern, line):
                if not is_in_block:
                    is_in_block = True
                    marker = re.match(code_pattern,line).group()
                else:
                    if marker == re.match(code_pattern,line).group():
                        is_in_block = False
                        marker = None

            if not is_in_block and re.match(title_pattern,line):
                temp_list = md_lines[current_idx:idx]
                content = "\n".join(temp_list)
                section_dict = {
                    "title": temp_list[0] if content.startswith("#") else "无标题",
                    "content":content,
                    "file_title":file_title
                }
                section_list.append(section_dict)
                current_idx = idx
        section_list.append(
            {
                "title":md_lines[current_idx],
                "content":"\n".join(md_lines[current_idx:]),
                "file_title":file_title
            }
        )




        spliter = RecursiveCharacterTextSplitter(
            chunk_size= 300,
            chunk_overlap=10,
            separators=["\n\n", "\n", "。", "！", "？", "；", ".", "!", "?", ";", " "]
        )

        chunk_size = 300
        final_section_list = []
        for section in section_list:
            content = section.get("content","")
            title = section.get("title","")
            real_content = content[len(title):] if content.startswith("#") else content
            if len(real_content) <= chunk_size:
                final_section_list.append(
                    {
                        **section,
                        "part":0
                    }
                )
                continue
            if "<table" in real_content:
                final_section_list.append(
                    {
                        **section,
                        "part":0
                    }
                )
                continue
            chunks = spliter.split_text(real_content)
            for idx,chunk in enumerate(chunks,start =1):
                final_section_list.append(
                    {
                        "title":title,
                        "content":chunk,
                        "file_title":file_title,
                        "part":idx
                    }
                )
        return final_section_list



if __name__ == '__main__':
    node = NodeDocumentSplit()
    init_state = {
        "md_path": r"E:\AI大模型\第七阶段 掌柜智库\掌柜智库05\07【掌柜智库】【导入】文档切片.md"
    }
    res = node(init_state)
    logger.info(convert_to_json(res))





