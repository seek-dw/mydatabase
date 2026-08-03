# atguigu/import_process/nodes/node_md_img.py
import base64
import os
import re
import time
from collections import deque
from pathlib import Path

from langchain.chat_models import init_chat_model

from atguigu.config.config import ModelConfig
from atguigu.import_process.base import NodeBase
from atguigu.import_process.state import ImportGraphState
from atguigu.tool.logger import logger


class NodeMDImg(NodeBase):
    """
    经过pdf_to_md节点后,该节点处理md文件中的图片,将图片转化为带有'摘要','urls'的格式
    #已知 md_path,md_content
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
                time.sleep(60-(current_time - dq[0]))
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
                    model = ModelConfig.qwen3vl_model_name,
                    model_provider = "openai",
                    api_key = ModelConfig.qwen3vl_api_key,
                    base_url = ModelConfig.qwen3vl_base_url,
                    temperature = ModelConfig.qwen3vl_model_temperature
                )
            res = llm.invoke(input = messages)
            image_with_summary_list.append(
                {
                    "image_name":image_with_context_str.get("image_name"),
                    "image_single_path":image_with_context_str.get("image_single_path"),
                    "summary":res.content
                }
            )
        return image_with_summary_list



if __name__ == '__main__':
    node = NodeMDImg()
    init_state = {
        "md_path": r"C:\Users\Administrator\Desktop\gitee\my_project\hak180产品安全手册\hak180产品安全手册.md"
    }
    res =node(init_state)
    logger.info(res)
