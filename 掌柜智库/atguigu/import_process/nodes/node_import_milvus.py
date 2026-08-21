# atguigu/import_process/nodes/node_import_milvus.py
import json

from pymilvus import DataType

from atguigu.config.config import MilvusConfig
from atguigu.import_process.base import NodeBase
from atguigu.import_process.state import ImportGraphState
from atguigu.tool.logger import logger
from atguigu.tool.milvus_client_create import get_milvus_client, ensure_collection_loaded


class NodeImportMilvus(NodeBase):
    """
    导入向量库节点：数据持久化
    1.获取包含了向量信息的chunks
    2.创建表
    3.把chunks放进表中(先进行幂等性删除,防止数据重复)
    """

    name = "node_import_milvus"

    def process(self, state: ImportGraphState):
        #获取chunks,并校验内容
        chunks = state.get("chunks","")
        if not chunks:
            logger.error("chunks为空,请检查您的输入")
            raise ValueError("chunks为空,请检查您的输入")
        #通过chunks拿到file_title
        file_title = chunks[0].get("file_title","")
        #通过chunks拿到稠密向量的dim
        dim = len(chunks[0].get("dense_vector"))


        #tool -> 拿到milvus客户端,准备创建表
        milvus_client  = get_milvus_client()
        if not milvus_client:
            logger.error("milvus_client 初始化失败")
            raise Exception("milvus_client 初始化失败")
        #指定表名
        # ==================== AI修改 开始 ====================
        # 教育导入可以通过 state 指定独立 collection；普通上传仍使用原 collection。
        # 这样旧知识库不需要先删表，教育数据可以平滑建立新 schema。
        # ==================== AI修改 结束 ====================
        collection_name = state.get("collection_name") or MilvusConfig.milvus_chunks_collection
        #判断表名是否存在使用has_collection(防止重复创建相同表)
        if not milvus_client.has_collection(collection_name=collection_name):
            #创建一个空的结构,并且指定自动生成id,省去了插入数据的时候传入id的麻烦
            #另外还有一个参数enable_dynamic_field，默认为False，表示是否启用动态字段,即插入未被定义的字段也不会报错
            schema = milvus_client.create_schema(
                auto_id=True
            )
            #添加字段
            # ==================== AI修改 开始 ====================
            # 教育实战需求：chunks表新增4个元数据字段，用于意图路由的标量过滤
            # content_type: course_intro(课程介绍)/question(题目)/doc(普通文档)
            # source_name: 来源文档名, code: 课程/题库/题目编码, q_type: 题型
            # 教育字段单独保存，支持课程/题库列表筛选和来源卡片展示。
            # 注意：schema已变更，旧collection不兼容，需在.env中修改CHUNKS_COLLECTION
            # 为新名称(或手动drop旧collection)后重新导入
            schema.add_field(
                field_name = "id",
                datatype = DataType.INT64,
                is_primary = True
            ).add_field(
                field_name = "file_title",
                datatype = DataType.VARCHAR,
                max_length = 200
            ).add_field(
                field_name = "title",
                datatype = DataType.VARCHAR,
                max_length = 1000
            ).add_field(
                field_name = "content",
                datatype = DataType.VARCHAR,
                max_length = 5000
            ).add_field(
                field_name = "item_name",
                datatype = DataType.VARCHAR,
                max_length = 200
            ).add_field(
                field_name = "part",
                datatype = DataType.INT64
            ).add_field(
                field_name = "dense_vector",
                datatype = DataType.FLOAT_VECTOR,
                dim = dim
            ).add_field(
                field_name = "sparse_vector",
                datatype = DataType.SPARSE_FLOAT_VECTOR
            ).add_field(
                field_name = "content_type",
                datatype = DataType.VARCHAR,
                max_length = 32
            ).add_field(
                field_name = "source_name",
                datatype = DataType.VARCHAR,
                max_length = 200
            ).add_field(
                field_name = "code",
                datatype = DataType.VARCHAR,
                max_length = 200
            ).add_field(
                field_name = "q_type",
                datatype = DataType.VARCHAR,
                max_length = 32
            ).add_field(
                field_name = "course_name",
                datatype = DataType.VARCHAR,
                max_length = 200
            ).add_field(
                field_name = "course_code",
                datatype = DataType.VARCHAR,
                max_length = 200
            ).add_field(
                field_name = "chapter_name",
                datatype = DataType.VARCHAR,
                max_length = 1000
            ).add_field(
                field_name = "course_category",
                datatype = DataType.VARCHAR,
                max_length = 200
            ).add_field(
                field_name = "target_users",
                datatype = DataType.VARCHAR,
                max_length = 500
            ).add_field(
                field_name = "learning_goals",
                datatype = DataType.VARCHAR,
                max_length = 500
            ).add_field(
                field_name = "project_name",
                datatype = DataType.VARCHAR,
                max_length = 200
            ).add_field(
                field_name = "question_bank_name",
                datatype = DataType.VARCHAR,
                max_length = 200
            ).add_field(
                field_name = "question_bank_code",
                datatype = DataType.VARCHAR,
                max_length = 200
            ).add_field(
                field_name = "question_code",
                datatype = DataType.VARCHAR,
                max_length = 200
            ).add_field(
                field_name = "question_type",
                datatype = DataType.VARCHAR,
                max_length = 32
            ).add_field(
                field_name = "source_path",
                datatype = DataType.VARCHAR,
                max_length = 1000
            )
            # ==================== AI修改 结束 ====================

            # 创建空的索引结构,返回的是一个INDEX_PARAMS对象
            index_params = milvus_client.prepare_index_params()
            # 对应的字段添加自定义的索引方法
            index_params.add_index(
                #添加索引的字段是"dense_vector"
                field_name = "dense_vector",
                #索引的类型 = 索引构建算法
                index_type = "IVF_FLAT", #inverted file index 倒排文件索引,聚类
                #相似度计算方式 = 查询的时候如何计算距离
                metric_type = "COSINE",
                #IVF参数 "nilst" 聚类数量 = 120, "nprobe":搜索参数
                params = {"nlist":120,"nprobe":12}
            )
            index_params.add_index(
                #添加索引的字段是"sparse_vector"
                field_name = "sparse_vector",
                #倒排索引 "苹果":page2,page3
                index_type = "SPARSE_INVERTED_INDEX",
                metric_type = "IP",
                params = {
                    "inverted_index_algo":"DAAT_MAXSCORE",
                    "NORMALIZE":True,
                    "quantization":"none"
                }
            )
            milvus_client.create_collection(
                collection_name = collection_name,
                schema = schema,
                index_params = index_params
            )

        #把chunks放入表中

        #幂等性删除
        #将数据从磁盘读取到内存中,方便操作,否则查询去磁盘查询速度非常慢
        # ==================== AI修改 开始 ====================
        # 原来直接调 load_collection, 多线程并发导入时6个线程同时load同一张表
        # 会触发Milvus内部锁竞争报错。改用幂等的 ensure_collection_loaded:
        # 先查load状态, 已加载就跳过(进程内缓存), 未加载才load, 避免重复load。
        # ==================== AI修改 结束 ====================
        ensure_collection_loaded(collection_name)
        #选取一个字段作为删除的条件,这里选择file_title
        #为了保证file_title内部特殊字符不会对查询条件造成影响,需要对file_title做转义处理
        # ==================== AI修改 开始 ====================
        # 修复原代码转义不完整的bug: 原来是.replace("'","\\").replace('"',"\\")
        # 反斜杠没有把特殊字符真正转义,查询条件会被特殊字符破坏,补全为\'和\"
        file_title = file_title.replace("\\","\\\\").replace("'","\\'").replace('"','\\"')
        # ==================== AI修改 结束 ====================
        milvus_client.delete(
            #删除的表名
            collection_name=collection_name,
            #删除条件
            filter=f"file_title == '{file_title}'"
        )
        #插入chunks

        # ==================== AI修改 开始 ====================
        # 1.新schema的content_type/source_name/code/q_type是非空字段
        # 普通文档上传(PDF/MD/DOCX)的chunks来自原切片管线,不含这些教育元数据字段
        # 插入前补默认值: content_type=doc表示普通文档,否则会报
        # "Insert missed an field `content_type`"错误
        # 2.(用户要求:不截断,保留完整信息) title上限已提高到1000,
        # 222字符的超长标题完整保留,零截断;下面的长度兜底与schema一致,
        # 只在极端情况下(>1000字符)才会触发,正常文档永远不会碰到
        # 注意: max_length只在建表时生效,旧collection(200上限)必须删除重建才支持新上限
        _FIELD_MAXLEN = {
            "file_title": 200, "title": 1000, "content": 5000,
            "item_name": 200, "content_type": 32, "source_name": 200,
            "code": 200, "q_type": 32, "course_name": 200,
            "course_code": 200, "chapter_name": 1000,
            "course_category": 200, "target_users": 500,
            "learning_goals": 500, "project_name": 200,
            "question_bank_name": 200, "question_bank_code": 200,
            "question_code": 200, "question_type": 32,
            "source_path": 1000,
        }
        for chunk in chunks:
            if "content_type" not in chunk or not chunk.get("content_type"):
                chunk["content_type"] = "doc"
            if "source_name" not in chunk or not chunk.get("source_name"):
                chunk["source_name"] = chunks[0].get("file_title", "")
            chunk.setdefault("code", "")
            chunk.setdefault("q_type", "")
            # ==================== AI修改 开始 ====================
            # 普通文档没有教育字段时补空值，保证旧导入链路兼容新 schema。
            for _field in (
                "course_name", "course_code", "chapter_name", "course_category",
                "target_users", "learning_goals", "project_name",
                "question_bank_name", "question_bank_code", "question_code",
                "question_type", "source_path",
            ):
                chunk.setdefault(_field, "")
            # 旧字段和教育语义字段保持同步，避免两套字段出现不一致。
            if not chunk.get("course_code") and chunk.get("content_type") == "course_intro":
                chunk["course_code"] = chunk.get("code", "")
            if not chunk.get("question_code") and chunk.get("content_type") == "question":
                chunk["question_code"] = chunk.get("code", "")
            if not chunk.get("question_type") and chunk.get("content_type") == "question":
                chunk["question_type"] = chunk.get("q_type", "")
            # ==================== AI修改 结束 ====================
            # 极端兜底: 超过schema上限才截断(正常文档不会触发,不影响信息完整性)
            for _f, _max in _FIELD_MAXLEN.items():
                _v = chunk.get(_f)
                if isinstance(_v, str) and len(_v) > _max:
                    chunk[_f] = _v[:_max]
        # ==================== AI修改 结束 ====================

        #返回的res是一个字典,包含了两个字段,一个字段是"insert_count",表示插入的条数,一个是ids,表示插入数据的id,这就是前面的auto_id就是没有传入id时自动生成的ids
        # ==================== AI修改 开始 ====================
        # 兼容已经存在的旧普通文档表：旧 schema 没有教育字段时只插入它认识的字段，
        # 新创建的教育表则保留完整结构化字段。Milvus 关闭 dynamic field 时不能传未知列。
        insert_chunks = chunks
        try:
            description = milvus_client.describe_collection(collection_name=collection_name)
            existing_fields = {
                field.get("name") for field in description.get("fields", [])
            }
            if existing_fields:
                insert_chunks = [
                    {key: value for key, value in chunk.items() if key in existing_fields}
                    for chunk in chunks
                ]
        except Exception as schema_error:
            # 描述接口在部分 Milvus 版本中不可用时，沿用完整字段插入，让真实异常暴露。
            logger.warning(f"读取 collection schema 失败，继续使用完整字段插入: {schema_error}")
        # ==================== AI修改 结束 ====================

        res = milvus_client.insert(
            collection_name = collection_name,
            data = insert_chunks
        )
        #拿出ids,添加到每一个chunks中
        ids = res.get("ids")
        for idx,chunk in enumerate(chunks):
            chunk["id"] = ids[idx]

        # with open(r"E:\AI大模型\第七阶段 掌柜智库\资料\05-设备手册汇总\doc\chunk_id.json","w",encoding="utf-8") as f:
        #     json.dump(chunks,f,ensure_ascii=False,indent=4)


        return {
            "chunks":chunks
        }

if __name__ == '__main__':
    node = NodeImportMilvus()
    with open("./data/chunks_with_vector.json","r",encoding="utf-8") as f:
        chunks = json.load(f)
    init_state = {
        "chunks":chunks
    }
    res = node(init_state)
    logger.info(res)
