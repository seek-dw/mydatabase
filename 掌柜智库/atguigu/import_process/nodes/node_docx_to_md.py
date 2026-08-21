# ==================== AI修改 开始 ====================
# 整个文件为教育实战新增：DOCX -> Markdown 转换节点
# 背景：教育需求文档中"课程文档/项目文档"大量为 docx 格式(17个课程docx + 2个项目docx)
# 方案：使用 python-docx 提取段落与表格,标题样式映射为 Markdown 标题,生成 md 文件后
#       复用原有的 node_md_img -> node_document_split -> ... 完整导入链路
# 依赖：pip install python-docx
# 注意：此方案提取纯文本(docx内嵌图片不提取),如需图片摘要可改走 LibreOffice 转 pdf 再走 MinerU 链路
import re
from pathlib import Path

from atguigu.import_process.base import NodeBase
from atguigu.import_process.state import ImportGraphState
from atguigu.tool.logger import logger


class NodeDocxToMD(NodeBase):
    """
    节点功能：将 docx 文档转换为 Markdown 文本文件
    实现思路：
        1.防御性校验 docx_path 存在且是文件
        2.使用 python-docx 按文档顺序遍历 body 元素（段落+表格）
        3.标题样式(Heading 1~4)映射为 Markdown 的 # ~ ####
        4.表格转为逐行文本(列之间用 | 分隔),保证知识点不丢
        5.写出 md 文件到 local_dir,交给 node_md_img 走后续链路
    """

    name = "node_docx_to_md"

    # 把 word 标题样式名映射为 markdown 井号层级
    @staticmethod
    def heading_level(style_name: str):
        # 样式名形如 "Heading 1" / "标题 1"
        match = re.search(r"(?:Heading|标题)\s*(\d)", style_name or "")
        if match:
            level = int(match.group(1))
            return min(level, 4)  # markdown 最多用到 ####
        return 0  # 非标题

    def process(self, state: ImportGraphState):
        # 1.防御性校验
        docx_path = state.get("docx_path", "")
        if not docx_path:
            logger.error("docx路径为空")
            raise Exception("请提供docx文件路径")
        docx_path_obj = Path(docx_path)
        if not docx_path_obj.exists() or not docx_path_obj.is_file():
            logger.error("docx路径错误")
            raise Exception("请提供正确的docx文件路径")

        # 依赖延迟导入,缺少 python-docx 时给出明确提示而不是 ImportError 裸抛
        try:
            from docx import Document
            from docx.table import Table
            from docx.text.paragraph import Paragraph
        except ImportError as e:
            raise Exception("缺少依赖 python-docx, 请先执行: pip install python-docx") from e

        # 2.按文档顺序遍历 body(段落与表格混排时保持原始顺序)
        document = Document(docx_path_obj)
        md_lines = []
        for element in document.element.body:
            tag = element.tag.split('}')[-1] if '}' in element.tag else element.tag
            if tag == 'p':
                paragraph = Paragraph(element, document)
                text = paragraph.text.strip()
                if not text:
                    continue
                level = self.heading_level(paragraph.style.name if paragraph.style else "")
                if level:
                    md_lines.append("#" * level + " " + text)
                else:
                    md_lines.append(text)
            elif tag == 'tbl':
                table = Table(element, document)
                for row in table.rows:
                    cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
                    md_lines.append("| " + " | ".join(cells) + " |")

        md_content = "\n\n".join(md_lines)
        if not md_content.strip():
            logger.error("docx解析后内容为空")
            raise Exception("docx文档内容为空或无法解析")

        # 3.写出 md 文件到 local_dir,复用后续 md 处理链路
        local_dir = state.get("local_dir", "") or str(docx_path_obj.parent)
        md_path = str(Path(local_dir) / (docx_path_obj.stem + "_converted.md"))
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)
        logger.info(f"docx转换md完成: {md_path}, 共{len(md_lines)}个内容块")

        return {
            "md_path": md_path,
            "md_content": md_content
        }


if __name__ == '__main__':
    node = NodeDocxToMD()
    init_state = {
        "docx_path": r"E:\AI大模型\课程文档.docx",
        "local_dir": r"E:\AI大模型\output"
    }
    res = node(init_state)
    logger.info(res)
# ==================== AI修改 结束 ====================
