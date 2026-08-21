# ==================== AI修改 开始 ====================
# 整个文件为教育实战新增：教育数据确定性解析器
#
# 【为什么需要这个文件】
# 课程介绍.md / 题目资料.md 是格式严格的结构化文档(标题层级固定、字段位置固定),
# 如果走前端的通用导入管线(AI切分+LLM识别),会有两个致命问题:
#   1. 一道题的题干/选项/答案/解析可能被切成多个chunk分别入库,
#      用户检索到题目却看不到答案,题目数据直接废掉
#   2. LLM识别"商品名"是概率性的,结构化数据里的系列名/题库名明明写在原文里,
#      用规则解析100%准确且零成本
# 所以这里用"确定性规则解析"(正则+行级状态机),保证切分粒度完全可控
#
# 【行级状态机思路】(两个parse函数都是同一个套路)
# 逐行扫描文件,用三个"状态变量"记住当前读到哪了:
#   cur_xxx     = 当前正在收集的块的名字(比如当前系列名/当前题库名)
#   cur_block   = 当前块的原始行缓冲区(临时攒行)
#   flush()     = "收尾函数"——遇到新块开始时,把上一块攒的内容打包成一个chunk
# 这是解析固定格式大文件的标准手法,任何语言都通用
# ==================== AI修改 结束 ====================
import re
from atguigu.tool.logger import logger

# ---- 预编译正则(模块加载时只编译一次,循环里复用,比每行重新compile快得多) ----
# 课程介绍.md里的系列编码行形如: "- **系列编码**: general_purpose_programming_foundation"
# \s*匹配任意空白,(.+)捕获编码本身
SERIES_CODE_RE = re.compile(r"-\s*\*\*系列编码\*\*:\s*(.+)")
# 题目资料.md里的题库编码行形如: "- 题库编码: general_purpose_programming_bank"
BANK_CODE_RE = re.compile(r"-\s*题库编码:\s*(.+)")
# 题目行形如: "- **题型**: 单选题"
Q_TYPE_RE = re.compile(r"-\s*\*\*题型\*\*:\s*(.+)")

# ==================== AI修改 开始 ====================
# 教育字段抽取规则：结构化字段必须来自原文，缺失时返回空字符串，
# 这样答案可以诚实展示“暂无数据”，不会因为字段缺失而编造课程信息。
COURSE_CODE_RE = re.compile(r"-\s*\*\*系列编码\*\*:\s*(.+)")
COURSE_CATEGORY_RE = re.compile(r"-\s*\*\*课程分类\*\*:\s*(.+)")
TARGET_USERS_RE = re.compile(r"-\s*\*\*适合人群\*\*:\s*(.+)")
LEARNING_GOALS_RE = re.compile(r"-\s*\*\*学习目标\*\*:\s*(.+)")
# MULTILINE 让 findall 能逐行扫描“### 课程”小节，而不是只检查整段文本首行。
COURSE_MODULE_RE = re.compile(r"^\s*-\s*\*\*(.+?)\*\*\s*$", re.MULTILINE)
# 去掉描述里的动作前缀“完成一个/一个”，只保留真正的项目名称。
PROJECT_NAME_RE = re.compile(r"(?:完成一个|一个)?([\u4e00-\u9fffA-Za-z0-9]*项目(?:实战|实践)?)")
# ==================== AI修改 结束 ====================


# ==================== AI修改 开始 ====================
def _match_text(pattern, text: str) -> str:
    """从课程系列原文提取一个字段；格式变化时返回空串而不是中断导入。"""
    match = pattern.search(text)
    return match.group(1).strip() if match else ""


def _extract_course_modules(block_text: str) -> list[str]:
    """提取“### 课程”小节下的模块名称，多个模块用顿号保存。"""
    course_section = block_text.split("### 课程", 1)[-1]
    return [name.strip() for name in COURSE_MODULE_RE.findall(course_section)]


def _extract_project_name(block_text: str) -> str:
    """从模块描述中提取项目相关名称，没有项目内容时保持为空。"""
    match = PROJECT_NAME_RE.search(block_text)
    return match.group(1).strip() if match else ""
# ==================== AI修改 结束 ====================


def parse_course_md(md_path: str):
    """
    解析课程介绍.md

    【文件长什么样】(看清楚结构才能看懂下面的解析逻辑)
        # 课程                          <- 文件总标题(忽略)
        ## 通用编程入门班               <- 二级标题 = 一个课程系列开始
        - **系列编码**: xxx             <- 系列的唯一编码
        - **描述**: ...
        ### 课程                        <- 固定的"课程"小节头
        - **语法基础与开发环境**        <- 一个课程模块(编码/课时/学时/描述)
          - 编码: xxx, 课时: 8, 学时: 16.00
        ## 通用编程项目班               <- 下一个系列开始(上一个系列到此结束)
        ...

    【切分策略: 一个课程系列一个chunk】
    把"系列元信息 + 该系列下全部课程模块"绑在同一个chunk里。
    为什么不切更细? 因为用户问"有哪些Python课程"需要看到整个系列的完整课程列表,
    切碎了答案就散了,一次检索命中不完整。

    【返回的chunk字段与Milvus库字段一一对应】
    title=系列名 / content=原文全文 / item_name=主体名(查询时按它过滤)
    content_type="course_intro"(查询侧靠它区分内容类型) / source_name=来源文件
    code=系列编码 / part=分片序号(这里一个系列一块,固定0)
    """
    with open(md_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    chunks = []
    cur_series = None      # 状态: 当前系列名。None表示还没遇到任何系列(文件头部)
    cur_block = []         # 状态: 当前系列攒下的原始行

    def flush():
        """
        收尾函数: 把cur_block攒的内容打包成一个chunk。
        在两个时机被调用: ①遇到下一个"## "系列标题时 ②文件读完时。
        用闭包直接读写外层的cur_series/cur_block,避免传参。
        """
        # 防御: 还没遇到任何系列,或当前块是空的,就没东西可打包
        if not cur_series or not cur_block:
            return
        block_text = "".join(cur_block).strip()
        # ==================== AI修改 开始 ====================
        # 同一份正文同时保留给向量检索和结构化查询，避免后续重复解析。
        code = _match_text(COURSE_CODE_RE, block_text)
        modules = _extract_course_modules(block_text)
        chunks.append({
            "title": cur_series,
            "content": block_text,
            "item_name": cur_series,
            "content_type": "course_intro",
            "source_name": "课程介绍",
            "code": code,
            "q_type": "",
            "part": 0,
            "course_name": cur_series,
            "course_code": code,
            "chapter_name": "、".join(modules),
            "course_category": _match_text(COURSE_CATEGORY_RE, block_text),
            "target_users": _match_text(TARGET_USERS_RE, block_text),
            "learning_goals": _match_text(LEARNING_GOALS_RE, block_text),
            "project_name": _extract_project_name(block_text),
            "source_path": str(md_path),
        })
        # ==================== AI修改 结束 ====================

    # ---- 逐行扫描主循环 ----
    for line in lines:
        # 二级标题"## " = 新系列开始。
        # 技巧: line.startswith("## ")天然不会匹配"### "(因为"###"开头是三个#,第二个字符不是空格),
        # 但为了可读性还是显式排除了一下
        if line.startswith("## ") and not line.startswith("###"):
            flush()                       # 先把上一个系列打包入库
            cur_series = line[3:].strip() # 记住新系列名(去掉"## "前缀)
            cur_block = [line]            # 新块的缓冲区从这行重新开始攒
        elif cur_series is not None:
            # 系列内的普通行,统统攒进缓冲区
            # 注意: "### 课程"小节头和课程模块行也会走到这里,整块保持原文最保险
            cur_block.append(line)
        # cur_series还是None说明还在文件头部("# 课程"总标题那几行),直接跳过
    flush()  # 别忘了最后一块——文件读完时循环里不会触发flush,必须手动收尾

    logger.info(f"课程介绍解析完成,共{len(chunks)}个课程系列chunk")
    return chunks


def parse_question_md(md_path: str):
    """
    解析题目资料.md

    【文件长什么样】(两层嵌套结构,比课程介绍多一层)
        # 题目                              <- 总标题(忽略)
        ## 通用程序设计题库                 <- 二级标题 = 一个题库开始
        - 题库编码: general_purpose_programming_bank
        ### general_purpose_programming_bank_q001   <- 三级标题 = 一道题开始
        - **题型**: 单选题
        - **题干**: 关于变量与常量的说法...
        - **选项**: A... B... C... D...
        - **答案**: B
        - **解析**: 常量用于表达业务中...
        ### general_purpose_programming_bank_q002   <- 下一道题开始
        ...

    【切分策略: 一道题一个chunk(全文件最关键的一条约束!)】
    题干+选项+答案+解析必须在同一个chunk里,一旦被切开:
    检索命中"题干chunk"时看不到答案,题库检索需求直接不达标。
    所以这里以"### "三级标题为切分点,题库级"## "只用来更新归属,不切分。

    【字段挂载】item_name=题库名(按题库过滤检索) / code=题目编码
    (需求说明要求"支持题目编码检索",这个字段就是给query侧用的)
    """
    with open(md_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    chunks = []
    cur_bank = None       # 状态: 当前题库名(题目的"归属")
    cur_bank_code = ""    # 状态: 当前题库编码
    cur_q_code = None     # 状态: 当前题目编码。None表示当前不在任何题目里
    cur_block = []        # 状态: 当前题目的原始行缓冲区

    def flush():
        """收尾: 把攒的一道题打包成chunk(遇到下一道题或下一个题库时调用)"""
        if not cur_q_code or not cur_block:
            return
        block_text = "".join(cur_block).strip()
        # 从题面文本里提取题型字段
        q_type_match = Q_TYPE_RE.search(block_text)
        q_type = q_type_match.group(1).strip() if q_type_match else ""
        chunks.append({
            "title": cur_q_code,
            # content头部显式拼上【题库】【题目编码】前缀——
            # 这样向量里包含了题库名信息,"XX题库第一题"这种问法也能被语义检索命中
            # ==================== AI修改 开始 ====================
            # 题库编码也放进正文前缀，保证“按题库编码提问”时稀疏向量能命中。
            "content": (
                f"【题库】{cur_bank}\n【题库编码】{cur_bank_code}\n"
                f"【题目编码】{cur_q_code}\n{block_text}"
            ),
            # ==================== AI修改 结束 ====================
            "item_name": cur_bank,
            "content_type": "question",
            "source_name": "题目资料",
            "code": cur_q_code,
            "q_type": q_type,
            "part": 0,
            # ==================== AI修改 开始 ====================
            # 题目字段同时保留兼容旧字段(code/q_type)，新接口使用语义更清晰的字段名。
            "course_name": "",
            "question_bank_name": cur_bank,
            "question_bank_code": cur_bank_code,
            "question_code": cur_q_code,
            "question_type": q_type,
            "chapter_name": "",
            "project_name": "",
            "source_path": str(md_path),
            # ==================== AI修改 结束 ====================
        })

    # ---- 逐行扫描主循环(注意分支顺序: 先判"## "再判"### ",互不干扰) ----
    for line in lines:
        if line.startswith("## ") and not line.startswith("###"):
            # 新题库开始: 先把最后一道没打包的题收尾,
            # 再重置题目状态(切到新题库后,旧题目不能再归到新题库名下)
            flush()
            cur_q_code = None
            cur_block = []
            cur_bank = line[3:].strip()
            # ==================== AI修改 开始 ====================
            # 切换题库时同步清空题库编码，避免格式不规范的资料把上一个题库编码带过来。
            cur_bank_code = ""
            # ==================== AI修改 结束 ====================
        elif line.startswith("- 题库编码:"):
            # 题库编码行: 单独提取存起来(字段级信息,不在题目chunk里重复)
            m = BANK_CODE_RE.match(line)
            cur_bank_code = m.group(1).strip() if m else ""
        elif line.startswith("### "):
            # 新题目开始: 先收尾上一道题,再开启新题缓冲区
            flush()
            cur_q_code = line[4:].strip()
            cur_block = [line]
        elif cur_q_code is not None:
            # 题目内的普通行(题型/题干/选项/答案/解析),攒进缓冲区
            cur_block.append(line)
        # cur_q_code还是None = 处在题库头部信息区(还没到第一道题),跳过
    flush()  # 文件读完,最后一道题手动收尾

    logger.info(f"题目资料解析完成,共{len(chunks)}个题目chunk")
    return chunks


def extract_item_names(course_chunks, question_chunks):
    """
    汇总需要注册到item主体库的名称: 课程系列名 + 题库名,去重保序。

    【为什么需要注册主体名】
    items表是查询链路"商品名确认"节点的候选池:
    用户提问时,系统拿问题向量去items表里找最像的主体名(题库名/系列名/文档商品名),
    命中了就按item_name过滤chunks表,大幅缩小检索范围提升准确率。
    教育数据的课程系列/题库注册进去后,"Python课程""程序设计题库"这类问题
    才能正确路由到对应数据。

    【去重手法】seen集合记录已见过的名字,O(1)判断是否重复;
    多个chunk可能挂同一个item_name(一个题库几百道题),必须去重,
    否则items表里重复插入同一个主体
    """
    names = []
    seen = set()
    for chunk in course_chunks + question_chunks:
        name = chunk.get("item_name", "")
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return names
