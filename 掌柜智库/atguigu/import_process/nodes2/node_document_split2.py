import re
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter

from atguigu.import_process.base import NodeBase
from atguigu.import_process.state import ImportGraphState
from atguigu.tool.convert_to_json import convert_to_json
from atguigu.tool.logger import logger


class NodeDocumentSplit(NodeBase):

    name = "node_document_split"

    def process(self,state:ImportGraphState):

        md_path = state.get("md_path")
        if not md_path:
            logger.error("路径不存在")
            raise Exception("路径不存在")
        md_path_obj = Path(md_path)
        if not md_path_obj.exists():
            logger.error("路径错误")
            raise Exception("错误的路径")

        with open(md_path_obj,"r",encoding="utf-8") as f:
            md_content = f.read()

        if not md_content:
            logger.info("文件无内容")
            raise Exception("文件无内容")

        file_title = state.get("file_title")
        if not file_title:
            file_title = md_path_obj.stem


        md_content.replace("\n\r","\n").replace("\r","\n")

        md_lines = md_content.split("\n")


        code_pattern = r"(^`{3,}|~{3,})"
        title_pattern = r"^\s*#{1,6}\s+.+"
        marker = None
        is_in_block = False
        current_idx = 0
        section_list = []
        for idx , line in enumerate(md_lines):
            line = line.strip()
            if re.match(code_pattern,line):
                if not is_in_block:
                    is_in_block = True
                    marker = re.match(code_pattern,line).group(1)
                else:
                    if marker == re.match(code_pattern,line).group(1):
                        is_in_block = False
                        marker = None

            if not is_in_block and re.match(title_pattern,line):
                content = "\n".join(md_lines[current_idx:idx])
                section_dict = {
                    "content":content,
                    "title":md_lines[current_idx:idx][0] if content.startswith("#") else "自定义标题",
                    "file_title":file_title
                }

                section_list.append(section_dict)

                current_idx = idx
        section_list.append({
            "content":"\n".join(md_lines[current_idx:]),
            "title":md_lines[current_idx],
            "file_title":file_title
        })

        print(convert_to_json(section_list))
        chunk_size = 200

        spliter = RecursiveCharacterTextSplitter(
            chunk_size = chunk_size,
            chunk_overlap = 20,
            separators = ["\n\n", "\n", "。", "！", "？", "；", ".", "!", "?", ";", " "]
        )
        final_section_list = []
        for section in section_list:
            content = section.get("content")
            title = section.get("title")
            real_content = content[len(title):] if content.startswith("#") else content
            if len(real_content)<chunk_size:
                final_section_list.append(
                    {
                        **section,
                        "part":0
                    }
                )
                continue
            if "<table" in real_content:
                final_section_list.append({
                    **section,
                    "part":0
                })
                continue
            chunk_list = spliter.split_text(real_content)
            for idx ,chunk in enumerate(chunk_list):
                final_section_list.append({
                    "title":title,
                    "content":title + chunk,
                    "file_title":file_title,
                    "part":idx
                })
        return final_section_list


if __name__ == '__main__':
    node = NodeDocumentSplit()
    init_state={
        "md_path": r"E:\AI大模型\第七阶段 掌柜智库\掌柜智库05\07【掌柜智库】【导入】文档切片.md"
    }
    res = node(init_state)
    logger.info(convert_to_json(res))