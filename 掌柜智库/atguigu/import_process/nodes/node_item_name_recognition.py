# atguigu/import_process/nodes/node_item_name_recognition.py
import json

from langchain.chat_models import init_chat_model
from pymilvus import DataType
from atguigu.config.config import ModelConfig, MilvusConfig
from atguigu.config.prompt import ITEM_NAME_SYSTEM_PROMPT, ITEM_NAME_USER_PROMPT_TEMPLATE
from atguigu.import_process.base import NodeBase
from atguigu.import_process.state import ImportGraphState
from atguigu.tool.bgem3_create_tool import  vectorize_texts
from atguigu.tool.logger import logger
from atguigu.tool.milvus_client_create import get_milvus_client


class NodeItemNameRecognition(NodeBase):
    """
    主体识别节点：主体识别与标签提取
    上节通过获取图片清洗后的md文件进行切分后的到了该文件的所有的chunks
    本节的目的就是给整个文章增加一个主体识别
    具体实现过程:
    1.获取chunks
    2.对chunks进行自定义切片,拿到最有可能包含主体信息的chunks
    3.将切分后的chunks拼接成一个新的大chunks字符串
    4.将大的字符串chunks交给大模型并设置提示词让其识别其主体名称
    5.创建milvus客户端并创建表
    6.将识别获取的主体名称向量化后插入milvus库

    """

    name = "node_item_name_recognition"

    def process(self, state: ImportGraphState):

        # 1.获取chunks
        chunks = state.get("chunks","")
        if not chunks:
            logger.error("chunks为空")
            raise Exception("chunks为空")
        file_title = state.get("file_title","")
        if not file_title:
            logger.error("file_title is  empty")
            raise Exception("file_title is empty")


        # 2.对chunks进行自定义切片,拿到最有可能包含主体信息的chunks
        # 3.将切分后的chunks拼接成一个新的大chunks字符串
        chunks_part_list = chunks[:3]+chunks[len(chunks)//2: len(chunks)//2 + 3]+chunks[-3:]
        max_len = 100000
        content_str = '\n'
        for idx , chunk in enumerate(chunks_part_list,start = 1):
            title = chunk.get("title")
            content = chunk.get("content")
            chunk_str = f"{idx}\n{file_title}\n{title}\n{content}\n"
            if len(content_str) > max_len:
                logger.info("超过最大长度,不在拼接")
                break
            content_str+=chunk_str
        content_str = content_str[:max_len]

        # 4.将大的字符串chunks交给大模型并设置提示词让其识别其主体名称

        llm = init_chat_model(
            model = ModelConfig.LLM_MODEL_NAME,
            model_provider = "openai",
            api_key = ModelConfig.VL_MODEL_API_KEY,
            base_url = ModelConfig.VL_MODEL_BASE_URL,
            temperature = ModelConfig.VL_MODEL_TEMPERATURE
        )

        messages = [
            {"role":"system","content":ITEM_NAME_SYSTEM_PROMPT},
            {"role":"user","content":ITEM_NAME_USER_PROMPT_TEMPLATE.format(file_title=file_title,content=content_str)}
        ]
        res = llm.invoke(input = messages)
        print(res.content)
        #拿取主体名称
        item_name = res.content
        #清洗llm输出的字符串文本,防止同一个主体文本在milvus中产生多个记录,这方法会误伤正常输出空格
        item_name = item_name.replace(" ","").replace("\n","").replace("\t","")

        if not item_name:
            item_name = file_title

        #创建milvus客户端
        milvus_client = get_milvus_client()
        #校验
        if not milvus_client:
            logger.error("milvus_client 初始化失败")
            raise Exception("milvus_client 初始化失败")
        #创建表名
        collection_name = MilvusConfig.milvus_item_collection
        #判断表名是否已经存在,若不存在,则创建
        if not milvus_client.has_collection(collection_name):

            #创建结构
            schema = milvus_client.create_schema(
                auto_id = True,
            )
            schema.add_field(
                field_name = "id",
                datatype = DataType.INT64,
                is_primary = True
            ).add_field(
                field_name = "item_name",
                datatype = DataType.VARCHAR,
                max_length = 100
            ).add_field(
                field_name = "file_title",
                datatype = DataType.VARCHAR,
                max_length = 100
            ).add_field(
                field_name = "dense_vector",
                datatype = DataType.FLOAT_VECTOR,
                dim = 1024
            ).add_field(
                field_name = "sparse_vector",
                datatype = DataType.SPARSE_FLOAT_VECTOR
            )

            # 创建索引
            index_params = milvus_client.prepare_index_params()
            index_params.add_index(
                field_name = "dense_vector",
                index_type = "IVF_FLAT", #暴力检索
                metric_type = "COSINE",
                params = {"nlist":200,"nrobe":20}
            )
            index_params.add_index(
                field_name = "sparse_vector",
                index_type = "SPARSE_INVERTED_INDEX", #倒排索引
                metric_type = "IP",
                params = {

                    #稀疏检索算法
                    "inverted_index_algo": "DAAT_MAXSCORE",
                    #归一化,让内积等价于余弦相似度
                    "normalize": True,
                    #关闭量化,保持原始精度, "sq8": 8-bit量化
                    "quantization": "none"
                }
            )
            #创建表完成
            milvus_client.create_collection(
                collection_name = collection_name,
                schema = schema,
                index_params = index_params
            )


        #插入数据之前先幂等性删除数据
        #由于过滤的条件是item_name是由大模型生成出来的不稳定因素,所以为了保证该字段被删除,需要对其内容做一个防止语法破坏的操作
        safe_item_name = item_name.replace("\\","\\\\").replace("'","\\").replace('"',"\\")

        #类似sql语句Delete * from collection_name where filter (item_name == xxxx)
        milvus_client.delete(collection_name,filter = (f"item_name == '{safe_item_name}'") )

        #幂等性删除完成后准备插入数据
        #将item_name通过嵌入式模型进行向量化
        item_name_vector = vectorize_texts([item_name])

        #准备插入数据
        data = {
            "item_name":item_name,
            "file_title":file_title,
            "dense_vector":item_name_vector.get("dense")[0],
            "sparse_vector":item_name_vector.get("sparse")[0]
        }

        #插入数据
        milvus_client.insert(
            collection_name = collection_name,
            data = data
        )

        #插入数据
        milvus_client.insert(
            collection_name = collection_name,
            data = []
        )

        #
        for chunk in chunks:
            chunk["item_name"] = item_name

        with open("data/item_chunk.json", "w", encoding="utf-8") as f:
            f.write(json.dumps(chunks,ensure_ascii=False,indent=4))

        return {
            "item_name":item_name,
            "chunks" : chunks
        }



if __name__ == '__main__':
    node = NodeItemNameRecognition()

    # with open("./chunk.json","r",encoding="utf-8") as f:
    #     chunks_json = f.read()
    # chunks = json.loads(chunks_json)
    #
    with open("data/chunk.json", "r", encoding="utf-8") as f:
        chunks = json.load(f)
    # print(chunks,type(chunks))
    init_state={
        "chunks":chunks,
        "file_title":"07【掌柜智库】【导入】文档切片"
    }
    res = node(init_state)
    logger.info(res)