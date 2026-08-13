from pymilvus import MilvusClient, AnnSearchRequest, WeightedRanker

from atguigu.config.config import MilvusConfig

milvus_client =None
def get_milvus_client():
    global milvus_client
    if not milvus_client:
        milvus_client = MilvusClient(
            uri= MilvusConfig.milvus_url
        )
    return milvus_client

#创建混合检索请求
def create_reqs(dense_data,
                sparse_data,
                dense_anns_field = None,
                sparse_anns_field = None,
                dense_param = None,
                sparse_param = None ,
                limit=10,
                expr=None):


    #创建稠密向量请求
    dense_req = AnnSearchRequest(
    data= [dense_data],
    anns_field= dense_anns_field,#要请求的字段
    param= dense_param,
    limit= limit,
    expr= expr
    )
    #expr过滤表达式,类似于mysql里面的where
    sparse_req = AnnSearchRequest(
        data=[sparse_data],
        anns_field=sparse_anns_field,  # 要请求的字段
        param=sparse_param,
        limit=limit,
        expr=expr
    )
    return [dense_req,sparse_req]

#创建混合检索方法:
def my_hybrid_search(collection_name,reqs,ranker=(0.5,0.5),limit=10,output_fields=None):
    milvus_client = get_milvus_client()

    """
    norm_score归一化,统一量纲:稠密向量的重排序分数和稀疏向量的重排序分数
    ranker[0],rank[1],对权重进行分配
    """
    #*nums权重分配顺序对应reqs的请求顺序
    weight_ranker = WeightedRanker(ranker[0],ranker[1],norm_score=True)

    res = milvus_client.hybrid_search(
        collection_name=collection_name,
        reqs = reqs,
        ranker = weight_ranker,
        limit= limit,
        output_fields = output_fields #返回会包含id 和 距离,除了这些你想自定义返回的字段
    )
    return res