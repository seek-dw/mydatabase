# atguigu/tool/eval_recall.py
# ==================== AI修改 开始 ====================
"""
召回率评测脚本
用法(在项目根目录,用项目venv运行):
    # 模式1: 自动从向量库生成评测集并评测(推荐,先跑这个)
    python -m atguigu.tool.eval_recall

    # 模式2: 评测前N个主体(快速抽检)
    python -m atguigu.tool.eval_recall --sample 20

    # 模式3: 使用自定义评测集(JSON文件)
    python -m atguigu.tool.eval_recall --file my_eval.json

自定义评测集格式(JSON数组,每个元素):
    {
        "query": "python数据分析课程讲什么",
        "expect_item_names": ["Python数据分析系列"],   # 可选: 期望命中的主体名
        "expect_keywords": ["pandas"]                  # 可选: 期望命中的内容关键词
    }

指标说明:
    Hit@K     : Top-K条结果中至少有1条命中期望 → 该query记1次命中
    Recall@K  : 期望的主体名/关键词被召回的比例(多期望时按条平均)
    MRR       : 第一条命中结果的排名倒数的平均值(排名越靠前分越高,1.0=全在首位)
评测原理: 完全复刻线上检索链路 node_search_embedding 的参数
    (BGE-M3稠密+稀疏双路向量 -> WeightedRanker(0.9,0.1)混合检索 -> Top-K),
    评测结果即线上真实召回水平,不是模拟。
"""
import argparse
import json
import os
import time

from atguigu.config.config import MilvusConfig
from atguigu.tool.bgem3_create_tool import vectorize_texts
from atguigu.tool.logger import logger
from atguigu.tool.milvus_client_create import create_reqs, get_milvus_client, my_hybrid_search

# 评测默认参数(与线上node_search_embedding完全一致)
RANKER_WEIGHTS = [0.9, 0.1]
# ==================== AI修改 开始 ====================
# 线上检索limit已从10提升到20(扩大初召回池喂饱rerank断崖检测),评测同步
SEARCH_LIMIT = 20          # 线上检索取Top20
EVAL_TOP_K = [1, 3, 5, 10, 20] # 在这几个K上分别算指标
# ==================== AI修改 结束 ====================
# 自动生成评测集的query模板(贴近用户真实问法,避免直接抄主体名造成虚高)
QUERY_TEMPLATES = {
    "course_intro": "{name}这门课主要讲什么内容",
    "question": "{name}题库里有哪几道题",
    "doc": "{name}的核心要点有哪些",
}
DEFAULT_CONTENT_TYPE_TEMPLATE = "doc"


def build_eval_set_from_milvus(sample: int = 0):
    """从chunks表自动生成评测集: 每个主体(item_name)生成一条query,
    ground truth就是该主体名下已有的chunk——这是最可靠的监督信号"""
    client = get_milvus_client()
    if not client:
        raise Exception("Milvus客户端初始化失败,请检查服务是否启动")
    collection = MilvusConfig.milvus_chunks_collection
    if not client.has_collection(collection):
        raise Exception(f"集合 {collection} 不存在,请先导入数据再评测")
    client.load_collection(collection)

    # 查出所有(主体名,内容类型)组合及其chunk数
    res = client.query(
        collection_name=collection,
        filter='item_name != ""',
        output_fields=["item_name", "content_type"],
        limit=16384,
    )
    counter = {}
    for row in res:
        name = row.get("item_name", "")
        ct = row.get("content_type", "doc")
        counter[(name, ct)] = counter.get((name, ct), 0) + 1

    eval_set = []
    items = sorted(counter.items(), key=lambda x: -x[1])  # chunk多的主体排前面
    if sample > 0:
        items = items[:sample]
    for (name, ct), cnt in items:
        template = QUERY_TEMPLATES.get(ct, QUERY_TEMPLATES[DEFAULT_CONTENT_TYPE_TEMPLATE])
        eval_set.append({
            "query": template.format(name=name),
            "expect_item_names": [name],
            "expect_content_type": ct,
            "chunk_count": cnt,
        })
    return eval_set


def search_one(query: str, expr: str = None):
    """复刻node_search_embedding的检索: 同样的向量、ranker权重、output_fields"""
    embed = vectorize_texts([query])
    dense_data = embed.get("dense")[0]
    sparse_data = embed.get("sparse")[0]
    reqs = create_reqs(
        dense_data=dense_data,
        sparse_data=sparse_data,
        dense_anns_field="dense_vector",
        sparse_anns_field="sparse_vector",
        dense_param={"metric_type": "COSINE"},
        sparse_param={"metric_type": "IP"},
        expr=expr,
    )
    res = my_hybrid_search(
        collection_name=MilvusConfig.milvus_chunks_collection,
        reqs=reqs,
        ranker=RANKER_WEIGHTS,
        output_fields=["id", "title", "file_title", "content", "item_name",
                       "content_type", "source_name", "code", "q_type"],
        limit=SEARCH_LIMIT,
    )
    return [
        {**item.get("entity", {}), "score": item.get("distance")}
        for item in res[0]
    ]


def evaluate_one(case: dict):
    """评测单条: 返回各K的命中情况与首个命中排名"""
    query = case["query"]
    expect_items = set(case.get("expect_item_names") or [])
    expect_kws = [k.lower() for k in (case.get("expect_keywords") or [])]
    expect_ct = case.get("expect_content_type")  # 自动生成的评测集才带

    results = search_one(query)
    # 命中判定: 主体名匹配 或 关键词出现在content里 (或content_type匹配,仅自动集)
    hit_ranks = []  # 每个期望目标的命中排名(1-based)
    for target in expect_items | set(expect_kws):
        rank = None
        for i, r in enumerate(results):
            content = (r.get("content") or "").lower()
            item_name = r.get("item_name") or ""
            if target in item_name or (target in content and target in expect_kws):
                rank = i + 1
                break
        if rank:
            hit_ranks.append(rank)
    # content_type附加判定: 自动集的期望类型应出现在Top10
    ct_hit = False
    if expect_ct:
        ct_hit = any(r.get("content_type") == expect_ct for r in results)

    n_targets = max(1, len(expect_items) + len(expect_kws))
    per_k = {}
    for k in EVAL_TOP_K:
        hits = sum(1 for rank in hit_ranks if rank <= k)
        per_k[k] = hits / n_targets
    first_rank = min(hit_ranks) if hit_ranks else None
    return {
        "query": query,
        "n_results": len(results),
        "hit": bool(hit_ranks),
        "ct_hit": ct_hit,
        "first_rank": first_rank,
        "recall_per_k": per_k,
        "top1_item": results[0].get("item_name") if results else "",
        "top1_title": results[0].get("title") if results else "",
    }


def run_eval(eval_set, out_path="eval_recall_report.json"):
    total = len(eval_set)
    logger.info(f"开始评测,共{total}条query,每条检索Top{SEARCH_LIMIT}...")
    stats = {k: 0.0 for k in EVAL_TOP_K}
    hit_count = 0
    mrr_sum = 0.0
    miss_cases = []
    details = []
    t0 = time.time()
    for i, case in enumerate(eval_set):
        try:
            r = evaluate_one(case)
        except Exception as e:
            logger.error(f"第{i + 1}条评测异常: {e}")
            continue
        details.append(r)
        for k in EVAL_TOP_K:
            stats[k] += r["recall_per_k"][k]
        if r["hit"]:
            hit_count += 1
            mrr_sum += 1.0 / r["first_rank"]
        else:
            miss_cases.append({"query": r["query"], "top1_item": r["top1_item"],
                               "top1_title": r["top1_title"]})
        if (i + 1) % 10 == 0:
            logger.info(f"进度 {i + 1}/{total}")

    summary = {
        "总query数": total,
        "指标": {
            f"Recall@{k}": round(stats[k] / total, 4) for k in EVAL_TOP_K
        },
        # ==================== AI修改 开始 ====================
        # Hit标签跟随SEARCH_LIMIT动态变化,避免limit改了标签还写死@10的误导
        f"Hit@{SEARCH_LIMIT}(至少命中一条的query占比)": round(hit_count / total, 4),
        # ==================== AI修改 结束 ====================
        "MRR(首个命中排名倒数的均值)": round(mrr_sum / total, 4),
        "评测耗时(秒)": round(time.time() - t0, 1),
        "评测配置": {
            "ranker权重(稠密,稀疏)": RANKER_WEIGHTS,
            "检索条数limit": SEARCH_LIMIT,
            "向量库": MilvusConfig.milvus_chunks_collection,
        },
        "未命中query清单": miss_cases[:50],
        "明细": details,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 52)
    print("           掌柜智库 召回率评测报告")
    print("=" * 52)
    print(f"  评测query数 : {total}")
    for k in EVAL_TOP_K:
        print(f"  Recall@{k:<3}   : {summary['指标'][f'Recall@{k}']:.2%}")
    # ==================== AI修改 开始 ====================
    print(f"  Hit@{SEARCH_LIMIT:<3}    : {summary[f'Hit@{SEARCH_LIMIT}(至少命中一条的query占比)']:.2%}")
    # ==================== AI修改 结束 ====================
    print(f"  MRR         : {summary['MRR(首个命中排名倒数的均值)']:.2%}")
    print(f"  耗时        : {summary['评测耗时(秒)']}s")
    if miss_cases:
        print("-" * 52)
        print(f"  未命中 {len(miss_cases)} 条(前10条):")
        for m in miss_cases[:10]:
            print(f"    ✗ {m['query']}  (Top1={m['top1_item'] or m['top1_title']})")
    print("=" * 52)
    print(f"  完整报告已保存: {os.path.abspath(out_path)}")
    return summary


def main():
    parser = argparse.ArgumentParser(description="掌柜智库召回率评测")
    parser.add_argument("--sample", type=int, default=0, help="只抽前N个主体评测(0=全部)")
    parser.add_argument("--file", type=str, default="", help="自定义评测集JSON路径")
    parser.add_argument("--out", type=str, default="eval_recall_report.json", help="报告输出路径")
    args = parser.parse_args()

    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            eval_set = json.load(f)
        logger.info(f"加载自定义评测集: {args.file},共{len(eval_set)}条")
    else:
        eval_set = build_eval_set_from_milvus(sample=args.sample)
        logger.info(f"从向量库自动生成评测集{len(eval_set)}条(每个主体一条query)")
        if not eval_set:
            logger.error("向量库中没有带item_name的数据,无法自动生成评测集")
            return
    run_eval(eval_set, out_path=args.out)


if __name__ == "__main__":
    main()
# ==================== AI修改 结束 ====================
