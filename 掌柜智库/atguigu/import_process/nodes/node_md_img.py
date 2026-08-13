# atguigu/import_process/nodes/node_md_img3.py
import base64
import os
import re
import time
from collections import deque
from pathlib import Path

from langchain.chat_models import init_chat_model
from minio.deleteobjects import DeleteObject

from atguigu.config.config import ModelConfig, MinioConfig
from atguigu.import_process.base import NodeBase
from atguigu.import_process.state import ImportGraphState
from atguigu.tool.logger import logger
from atguigu.tool.minio_client_tool import create_minio_client


class NodeMDImg(NodeBase):
    """
    上一个节点拿到了md_path 和 md_content将pdf转化为md
    这一节主要处理一下md文件中的图片,目的获得图片的摘要和url替换原图
        摘要是给模型看的,防止后续rag检索丢失图片信息
        url是给前端用的,检索到相关内容前端可以直接拿到url返回原图

    #关键要素:图片附近上下文(per_content、follow_content)、图片的内容(base64_str)

    1.拿到md文件内容并创造图片存放目录和所有图片文件列表
        1.防御
        2.文件读写流读出内容 (防御)
        3.构造图片目录,并列出目录下每一个文件,判断是否满足图片后缀要求
    2.拿到上下文和图片的内容(二进制)
        1.防御,判断图片的格式是否支持
        2.使用正则解析匹配图片拿到图片的跨度索引
        3.拿到索引后通过切片拿到图片附近的上下文
    3.根据上下文和图片内容获得摘要
        1.准备视觉大模型
        2.利用滑动窗口算法规避大模型的限频
        3.调用大模型(因为是视觉大模型,提示词官网找)
    4.获得url并将全文内容替换并备份
        1.构建上传目录,构建客户端获取工具获取客户端,对上传目录幂等性删除
        2.上传图片,拼接url,构造新的带有url列表
        3.遍历该列表,使用正则替换摘要和url,备份为新文件
    """

    name = "node_md_img"

    def process(self, state: ImportGraphState):

    #1.拿到md文件内容
        #1.防御
        md_path = state.get("md_path", "")
        if not md_path:
            logger.error("路径不存在")
            raise Exception("请提供md文件路径")
        md_path_obj = Path(md_path)
        if not md_path_obj.exists():
            logger.error("路径错误")
            raise Exception("请提供正确的md文件路径")

    #2.读取文件内容
        #with open()后面既可以接path对象,也可以接字符串路径
        with open(md_path_obj, "r", encoding="utf-8") as f:
            md_content = f.read()
        #防御
        if not md_content:
            logger.error("md文件内容为空")
            raise Exception("文件内容为空")

        logger.info("md文件内容读取成功")


    #3.构造图片目录,并且列出目录下所有图片
        #构造图片存放目录
        images_dir_path_obj = md_path_obj.parent / "images"
        #防御
        if not images_dir_path_obj.exists():
            logger.error("图片目录不存在")
            raise Exception("请提供图片目录")
        #列出该目录下所有文件,os.listdir()遍历该目录下的所有文件,遍历出来后返回的娥是一个列表
        #os.listdir传递path对象或者是字符串都可以,但是返回的就是一个字符串列表
        image_name_list = os.listdir(images_dir_path_obj)
        # print(image_name_list)
        #如果没有图片,不需要处理图片,直接返回md文件内容
        if not image_name_list:
            return {
                "md_content":md_content
            }

    #3.根据正则匹配拿到图片的跨度索引,再进行切片拿到图片附近的上下文
        #遍历所有图片
        #所有图片格式
        image_with_context_str_list = []
        image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
        length = 200
        for image_name in image_name_list:
            #先判断该图片是否符合图片格式
            if Path(image_name).suffix.lower() not in image_extensions:
                logger.warning("图片格式错误")
                continue
            #图片格式符合要求,进行正则匹配
            """
            匹配 Markdown 图片引用格式 ![描述](路径)，定位图片在文档中的位置。
            使用非贪婪匹配避免跨越多个图片引用，使用 re.escape 转义图片名中的特殊字符，
            通过 match.span() 获取图片索引，用于截取图片上下文辅助视觉模型生成摘要。
            """
            pattern = re.compile(r"!\[.*?\]\(.*?" + re.escape(image_name) + r"\)")
            #match返回要给对象,对象中包含了span跨度索引
            match = pattern.search(md_content)
            # print(match)
            if not match:
                logger.error(f"图片{image_name}未被引用")
                continue
            #解包
            start, end = match.span()
            #上文
            pre_context = md_content[max(0,start-length):start]
            #下文
            follow_context = md_content[end:min(len(md_content),end+length)]

            # 拿到每个图片的路径
            # 此处的image_name是字符串, / 的左边必须是Path对象,右边可以任意拼接
            image_single_path = images_dir_path_obj / image_name

            #图片的内容
            with open(image_single_path,"rb") as f:
                image_content = f.read() #这里拿到的是<class bytes>一堆二进制内容
                #base64将二进制内容转化为可打印的字符串
                # base64模块.b64encode(二进制编码内容)方法,把内容从二进制转化为字符串但是还是<class bytes>
                # .decode("utf-8")方法,继续把<class bytes>转化为<class str>
                #输出base64_str就是图片经过base64编码解码后的文本表示
                every_image_base64_str = base64.b64encode(image_content).decode("utf-8")
                # print(base64_str)

            #拿到带有上下文和图片内容的列表
            image_with_context_str_list.append(
                {
                    "image_single_path":image_single_path,
                    "pre_context":pre_context,
                    "follow_context":follow_context,
                    "image_name":image_name,
                    "every_image_base64_str":every_image_base64_str
                }
            )


    #5.根据上下文和图片内容获得摘要
        #因为大模型会进行限频,考虑这一因素,在发送请求的时候采用滑动窗口算法限制单位时间内给大模型发送请求的次数
        #创建一个双向队列(同时满足左出右进,左进右出)(此处没用到只用到了单向)
        dq = deque(maxlen=20)
        llm = None
        image_with_summary_list = []
        for image_with_context_str in image_with_context_str_list:
            #每张图片的发送请求的当前时间
            current_time = time.time()
            #判断队列是否为空,并判断当前时间离第一个请求是否超过单位规定时间
            #如果超过规定时间则代表该图片可以发送请求,否则只能等待
            while dq and current_time - dq[0] > 60:
                #超过单位规定时间,清楚过期的请求记录
                dq.popleft()
            #来到这里说明while条件不满足,则需视情况是否等待
            #如果队列满员,则需要进行等待
            if dq and len(dq) == dq.maxlen:
                #current_time-dq[0]代表dq[0]离现在已经过去多长时间
                #60-(current_time - dq[0])代表距离规定单位时间还剩多少时间,就是需要等待的时间
                need_wait_time = max(
                    0,
                    60 - (current_time - dq[0])
                )
                time.sleep(need_wait_time)
                #睡眠完成,重置现在时间
                current_time = time.time()
                #等待时间已到,再次判断,这次应该是大于60了,所以清除旧记录,更新新的记录
                while dq and current_time - dq[0] > 60:
                    dq.popleft()
            #记录所有请求的时间戳
            dq.append(current_time)

            #构造提示词并调用大模型
            #优先基于官方文档的提示词进行编写
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                # 这个格式就是base64在使用的时候的规定
                                "url": "data:image/jpeg;base64," + every_image_base64_str,
                            },
                        },
                        {"type": "text", "text": f"""
                                                    这是一张图片，图片上文部分为"{image_with_context_str.get("pre_context")}"，
                                                    下文部分为"{image_with_context_str.get("follow_context")}"，
                                                    请用中文简要总结这张图片的摘要,字数在50字以内。"""
                         },
                    ],
                },
            ]
            if not llm :
                llm = init_chat_model(
                    model = ModelConfig.VL_MODEL_NAME,
                    model_provider = "openai",
                    api_key = ModelConfig.VL_MODEL_API_KEY,
                    base_url = ModelConfig.VL_MODEL_BASE_URL,
                    temperature = ModelConfig.VL_MODEL_TEMPERATURE
                )
            res = llm.invoke(input = messages)
            image_with_summary_list.append(
                {
                    "image_name":image_with_context_str.get("image_name"),
                    "image_single_path":image_with_context_str.get("image_single_path"),
                    "summary":res.content
                }
            )

    # 6.获得url地址
        #构造一个minio的上传图片存储路径
        upload_dir = MinioConfig.MINIO_IMG_DIR
        #获取minio客户端
        minio_client = create_minio_client()

        #幂等性删除,上传新数据之前先删除旧数据
        #先列出目录下面的老数据,返回的是一个生成器对象,遍历出来之后是一个个的object对象,只找前缀为upload_dir的对象
        old_image_list = minio_client.list_objects(
            bucket_name = MinioConfig.MINIO_BUCKET_NAME,
            prefix = upload_dir,
            recursive = True)

        #然后删除旧数据.返回一个生成器对象
        errors = minio_client.remove_objects(
            bucket_name = MinioConfig.MINIO_BUCKET_NAME,
            #删除数据只支持delete_object类型,所以要转一下类型
            delete_object_list= [DeleteObject(obj.object_name) for obj in old_image_list]
        )
        #真正执行删除
        for error in errors:
            logger.error( error)

        #准备上传图片

        image_with_summary_and_url_list=[]
        for image_with_summary in image_with_summary_list:
            minio_client.fput_object(
                bucket_name = MinioConfig.MINIO_BUCKET_NAME,
                object_name = upload_dir + "/"+image_with_summary.get("image_name"),
                file_path = image_with_summary.get("image_single_path")
            )

        #获取url地址
            url = f"http://{MinioConfig.MINIO_ENDPOINT}/{MinioConfig.MINIO_BUCKET_NAME}/{upload_dir}/{image_with_summary.get('image_name')}"
            image_with_summary_and_url_list.append(
                {
                    **image_with_summary,
                    "url":url
                }
            )


        #url+摘要都已经获取,现在替换原md文件中的 图片并重命名备份文件
        #使用正则匹配到每一站图片然后进行替换
        for image_with_summary_and_url in image_with_summary_and_url_list:
            pattern = re.compile(r"!\[.*?\]\(.*?" + re.escape(image_with_summary_and_url.get("image_name")) + r"\)")
            #pattern.sub(新内容,要替换的原文),pattern中自带匹配条件
            md_content = pattern.sub(
                f"![{image_with_summary_and_url.get('summary')}]({image_with_summary_and_url.get('url')})",
                md_content
            )
            #备份新的md文件
            new_md_path_obj = md_path_obj.parent / (md_path_obj.stem + "_backup.md")
            with open(new_md_path_obj, "w", encoding="utf-8") as f:
                f.write(md_content)
                logger.info(f"{md_path_obj}备份成功,备份文件路径为:{new_md_path_obj}")

        return {"md_content":md_content}



if __name__ == '__main__':
    node = NodeMDImg()
    pdf_list = [
        r"E:\AI大模型\第七阶段 掌柜智库\资料\05-设备手册汇总\doc\hak180产品安全手册\hak180产品安全手册.md"
    ]
    results = []  # 收集所有文件的结果
    for pdf_path in pdf_list:
        state = {
            "md_path": pdf_path,
        }
        res = node(state)
        results.append(res)
    # ============ 汇总 ============
    logger.info(f"共 {len(pdf_list)} 个文件，成功 {len(results)} 个")
    for r in results:
        logger.info(r)