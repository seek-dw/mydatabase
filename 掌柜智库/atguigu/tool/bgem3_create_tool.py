#单例模式创建嵌入模型,并实现向量化方法
from pymilvus.model.hybrid import BGEM3EmbeddingFunction

from atguigu.config.config import EmbeddingConfig
from atguigu.tool.convert_to_json import convert_to_json
from atguigu.tool.logger import logger

bgem3_model = None

#创建嵌入模型
def get_bgem3_model():
    global bgem3_model
    #单例
    if not bgem3_model:
        bgem3_model = BGEM3EmbeddingFunction(
            #此处上传的是模型的路径
            model_name = EmbeddingConfig.EMBEDDING_MODEL,
            device = EmbeddingConfig.DEVICE,
            use_fp16 = EmbeddingConfig.USE_FP16,
        )
    return bgem3_model


#创建向量化方法
def vectorize_texts(texts):
    bgem3_model = get_bgem3_model()
    #该方法接收一个List[str]作为输入
    embed_texts = bgem3_model.encode_documents(texts)
    # print(embed_texts)
    return {
        "dense":[dense.tolist() for dense in embed_texts.get("dense")],
        "sparse":[dict(zip( sparse.indices.tolist(),sparse.data.tolist() ))  for sparse in embed_texts.get("sparse")
        ]
    }


if __name__ == '__main__':
    texts = ["你好世界","你好尚硅谷"]
    res = vectorize_texts(texts)
    logger.info(convert_to_json(res))