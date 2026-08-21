#单例模式创建嵌入模型,并实现向量化方法
import threading

from pymilvus.model.hybrid import BGEM3EmbeddingFunction

from atguigu.config.config import EmbeddingConfig
from atguigu.tool.convert_to_json import convert_to_json
from atguigu.tool.logger import logger

bgem3_model = None

# ==================== AI修改 开始 ====================
# BGE-M3 内部使用 PyTorch/CUDA 原生对象，不能让多个导入线程同时初始化
# 或同时执行 encode_documents；否则 Windows 可能出现 0xC0000005 访问冲突。
# 只锁模型本身，不锁文档解析、切分和写入向量库，保留文件级并发能力。
_bgem3_init_lock = threading.Lock()
_bgem3_encode_lock = threading.Lock()
# ==================== AI修改 结束 ====================

#创建嵌入模型
def get_bgem3_model():
    global bgem3_model
    # ==================== AI修改 开始 ====================
    # 双重检查锁：已加载模型不加锁快速返回；首次加载时确保只有一个线程初始化。
    if bgem3_model is None:
        with _bgem3_init_lock:
            if bgem3_model is None:
                bgem3_model = BGEM3EmbeddingFunction(
                    #此处上传的是模型的路径
                    model_name = EmbeddingConfig.EMBEDDING_MODEL,
                    device = EmbeddingConfig.DEVICE,
                    use_fp16 = EmbeddingConfig.USE_FP16,
                )
    # ==================== AI修改 结束 ====================
    return bgem3_model


#创建向量化方法
def vectorize_texts(texts):
    model = get_bgem3_model()
    # ==================== AI修改 开始 ====================
    # 只串行化共享 BGE-M3 的实际推理调用，避免 CUDA 原生线程冲突；
    # 上游文档解析/切片和下游 Milvus 写入仍然可以并发执行。
    with _bgem3_encode_lock:
        #该方法接收一个List[str]作为输入
        embed_texts = model.encode_documents(texts)
    # ==================== AI修改 结束 ====================
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
