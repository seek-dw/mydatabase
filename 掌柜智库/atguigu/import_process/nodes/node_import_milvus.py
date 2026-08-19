# atguigu/import_process/nodes/node_import_milvus.py
import json

from pymilvus import DataType

from atguigu.config.config import MilvusConfig
from atguigu.import_process.base import NodeBase
from atguigu.import_process.state import ImportGraphState
from atguigu.tool.logger import logger
from atguigu.tool.milvus_client_create import get_milvus_client


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
        collection_name = MilvusConfig.milvus_chunks_collection
        #判断表名是否存在使用has_collection(防止重复创建相同表)
        if not milvus_client.has_collection(collection_name=collection_name):
            #创建一个空的结构,并且指定自动生成id,省去了插入数据的时候传入id的麻烦
            #另外还有一个参数enable_dynamic_field，默认为False，表示是否启用动态字段,即插入未被定义的字段也不会报错
            schema = milvus_client.create_schema(
                auto_id=True
            )
            #添加字段
            schema.add_field(
                field_name = "id",
                datatype = DataType.INT64,
                is_primary = True
            ).add_field(
                field_name = "file_title",
                datatype = DataType.VARCHAR,
                max_length = 100
            ).add_field(
                field_name = "title",
                datatype = DataType.VARCHAR,
                max_length = 100
            ).add_field(
                field_name = "content",
                datatype = DataType.VARCHAR,
                max_length = 5000
            ).add_field(
                field_name = "item_name",
                datatype = DataType.VARCHAR,
                max_length = 100
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
            )

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
        milvus_client.load_collection(collection_name=collection_name)
        #选取一个字段作为删除的条件,这里选择file_title
        #为了保证file_title内部特殊字符不会对查询条件造成影响,需要对file_title做转义处理
        file_title = file_title.replace("\\","\\\\").replace("'","\\").replace('"',"\\")
        milvus_client.delete(
            #删除的表名
            collection_name=collection_name,
            #删除条件
            filter=f"file_title == '{file_title}'"
        )
        #插入chunks

        #返回的res是一个字典,包含了两个字段,一个字段是"insert_count",表示插入的条数,一个是ids,表示插入数据的id,这就是前面的auto_id就是没有传入id时自动生成的ids
        res = milvus_client.insert(
            collection_name = collection_name,
            data = chunks
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