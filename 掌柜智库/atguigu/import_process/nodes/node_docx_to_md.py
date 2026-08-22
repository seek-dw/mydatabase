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
        # word里面的标题样式为Heading 1 / 标题 1
        # 搭配使用正则(?:...)非捕获组,使得group(1)精准抓取到标题组
        match = re.search(r"(?:Heading|标题)\s*(\d)", style_name or "")
        if match:
            level = int(match.group(1))
            return min(level, 4)  # markdown 最多用到 #### 将标题层级强制定为最多4级
        return 0  # 非标题

    def process(self, state: ImportGraphState):
        # 1.防御性校验
        docx_path = state.get("docx_path", "")
        if not docx_path:
            logger.error("docx路径为空")
            raise Exception("请提供docx文件路径")
        docx_path_obj = Path(docx_path)
        # .exists()判断路径是否存在, .is_file()判断路径是否是文件
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
        # 将路径对象转化为python当中的document对象
        document = Document(docx_path_obj)
        md_lines = []
        #直接遍历docx文档底层的xml的body结构获取每个元素
        for element in document.element.body:
            # 对tag切分tag包含命名空间和元素,只取元素,先用split切分tag字符串,形成列表.然后}后面的元素直接
            # 通过-1索引拿到手,拿到了元素之后再根据它是段落还是表格进行文本处理
            tag = element.tag.split('}')[-1] if '}' in element.tag else element.tag
            if tag == 'p':
                # 重新将xml的元素和document对象绑定,使得paragraph对象知道自己的文档结构
                paragraph = Paragraph(element, document)
                # 取出文本
                text = paragraph.text.strip()
                # 空段落:跳过
                if not text:
                    continue
                # 如果有文本,正则匹配,匹配到了标题
                # 如果段落的style对象存在
                level = self.heading_level(paragraph.style.name if paragraph.style else "")
                if level:
                    # 如果匹配到了标题,则对应markdown格式并添加到md_lines列表当中
                    md_lines.append("#" * level + " " + text)
                else:
                    # 没匹配到直接添加,到此完成了docx-md的文本内容以及标题的提取和转化
                    md_lines.append(text)

            elif tag == 'tbl':
                # 吧xml表格绑定document对象,成为python-docx的对象
                table = Table(element, document)\
                # 遍历每一行
                for row in table.rows:
                    # 遍历每一行的每一个单元格,并拿出文本内容进行空白字符的去除以及换行符替换为空格
                    cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
                    # 把表格转化为|xxx|markdown风格 | xx | xx |
                    md_lines.append("| " + " | ".join(cells) + " |")

        # 每个内容块中间添加2个换行
        md_content = "\n\n".join(md_lines)
        if not md_content.strip():
            logger.error("docx解析后内容为空")
            raise Exception("docx文档内容为空或无法解析")

        # 3.写出 md 文件到 local_dir,复用后续 md 处理链路
        # 优先使用local_dir , 没有的话使用原上传路径
        local_dir = state.get("local_dir", "") or str(docx_path_obj.parent)
        # md文档路径拼接
        md_path = str(Path(local_dir) / (docx_path_obj.stem + "_converted.md"))
        # 文件流写入文件
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
