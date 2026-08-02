# atguigu/import_process/nodes/node_pdf_to_md.py
import shutil
from pathlib import Path

from atguigu.config.config import MinerUConfig
from atguigu.import_process.base import NodeBase
from atguigu.import_process.state import ImportGraphState
from atguigu.tool.logger import logger


class NodePDFToMD(NodeBase):
    """
    PDF 转 Markdown 节点：PDF结构化解析
    """

    name = "node_pdf_to_md"

    def process(self, state: ImportGraphState):
        """
        #已知:文件类型,文件名,文件的本地目录
             -----防御性编程不多说,哪些需要使用的目录都要进行防御性编程-----
        1.本地文件批量上传:
            1.直接向解析PDF文件的服务器发请求(具体请求格式要对接官方文档),做出判断,拿到回执response
            2.从response中解析到本次请求的令牌batch_id,urls(服务器分发的远程上传资源地址)
            3.真正的上传,for循环把本地的文件目录一个个对应上传到每一个urls,判断是否上传成功
        2.结果解析:
            1.(轮询)直接从官网找到对应的格式进行修改,利用batch_id和urls返回解析后的'md'压缩文件资源地址
        3.下载解压重命名保存一条龙:
            1.下载:get请求得到的zip_urls资源地址,获得压缩内容,通过文件操作,写入某个文件
            2.解压:构造解压路径,判断是否为空,然后解压即可
            3.重命名:解压后默认名字是官方定的,保存,文件落盘

        :param state:
        :return:
        """
        #防御
        pdf_path = state.get("pdf_path","")
        if not pdf_path:
            logger.error("路径不存在")
            raise Exception("请提供PDF文件路径")

        pdf_path_obj = Path(pdf_path)
        if not pdf_path_obj.exists():
            logger.error("路径错误")
            raise Exception("请提供正确的PDF文件路径")

        local_dir = state.get("local_dir","")
        if not local_dir:
            logger.error("路径不存在")
            raise Exception("请提供本地目录")
        local_dir_obj = Path(local_dir)
        if not local_dir_obj.exists():
            logger.error("路径错误")
            raise Exception("请提供正确的本地目录")

        #1.直接向解析PDF文件的服务器发请求(具体请求格式要对接官方文档),做出判断,拿到回执response
        import requests
        token = MinerUConfig.MINERU_API_KEY
        #请求地址,获取上传地址的接口
        url = "https://mineru.net/api/v4/file-urls/batch"
        #请求头格式,具体格式需要看接口的要求
        header = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        #真正的请求内容
        data = {
            "files": [
                {"name": f"{pdf_path_obj.stem}.pdf", "data_id": "abcd"}
            ],
            "model_version": "vlm"
        }
        #本地上传路径
        file_path = [f"{pdf_path}"]
        #正式提交请求,并将数据转化为了json串,拿到了回执response
        response = requests.post(url, headers=header, json=data,timeout=10)

    #2.从response中解析到本次请求的令牌batch_id,urls(服务器分发的远程上传资源地址)
        if response.status_code != 200:
            logger.error("请求失败")
        logger.info("请求成功")
        #反序列化取值
        result = response.json()
        # print(result)
        if result["code"] != 0:
            logger.error("请求数据返回失败")
        logger.info("请求数据返回成功")
        batch_id = result["data"]["batch_id"]
        urls = result["data"]["file_urls"]

    #3.真正的上传,for循环把本地的文件目录一个个对应上传到每一个urls,判断是否上传成功
        #没必要用for,这段代码只能传单个文件
        import time
        for i in range(0, len(urls)):
            with open(file_path[i], 'rb') as f:
                res_upload = requests.put(urls[i], data=f)
                if res_upload.status_code == 200:
                    logger.info(f"{urls[i]} 上传成功")
                else:
                    logger.error(f"{urls[i]} 上传失败")



    #4.post提交,get查询,这里要进行轮询,一直请求直到服务器给结果
        token = MinerUConfig.MINERU_API_KEY
        batch_id = batch_id
        url = f"https://mineru.net/api/v4/extract-results/batch/{batch_id}"
        header = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        total_time = 300
        use_time = 0
        while True:
            start_time = time.time()
            try:
                response = requests.get(url, headers=header,timeout=10)
                if response.status_code != 200:
                    logger.error("请求失败")
                    raise Exception("请求失败")
                result = response.json()
                # print(result)
                if result["code"] != 0:
                    logger.error("请求数据返回失败")
                    raise Exception("请求数据返回失败")
                extract_result = result['data']['extract_result'][0]
                #all()里面元素都为真才返回真
                if extract_result['state'] != "done":
                    logger.info("正在处理中...")
                    raise Exception("正在处理中...")
                md_zip_urls =extract_result['full_zip_url']
                # print(md_zip_urls)
                break
            except Exception:
                end_time = time.time()
                use_time += (end_time - start_time)
                if use_time > total_time:
                    logger.error("处理超时")
                    raise Exception("处理超时")
                continue

    # 1.下载:get请求得到的zip_urls资源地址,获得压缩内容,通过文件操作,写入某个文件

        import requests

        zip_res  = requests.get(md_zip_urls,timeout=10)
        if zip_res.status_code != 200:
            logger.error("请求失败")
            raise Exception("请求失败")
        zip_content = zip_res.content
    #默认打印对象,内容使用.content,接口解析使用.json,文本内容使用.text
    # print(response.content)

    #构造下载地址
        md_zip_path_obj = local_dir_obj / f"{pdf_path_obj.stem}.zip"
        #文件写入
        with open(md_zip_path_obj, "wb") as f:
            f.write(zip_content)

    #2.解压:
        import zipfile
        #获得解压对象
        unzip_file_content = zipfile.ZipFile(md_zip_path_obj)
        #构造加压目录
        unzip_file_path_obj = local_dir_obj / f"{pdf_path_obj.stem}"
        #对目录做判断
        if  unzip_file_path_obj.exists():
            shutil.rmtree(unzip_file_path_obj)
        #parents = True, 中间目录不存在自动创建,exist_ok = True, 存在不会报错
        unzip_file_path_obj.mkdir(parents = True, exist_ok = True)
        #解压到指定目录
        unzip_file_content.extractall(unzip_file_path_obj)
        logger.info("解压成功")

#3.重命名+保存
        origin_unzip_path_obj = unzip_file_path_obj / "full.md"
        #返回了一个新的path对象,只是对象中改了名,但是磁盘没有变化
        new_unzip_path_obj = origin_unzip_path_obj.with_name(f"{pdf_path_obj.stem}.md")
        #真正的操作系统,磁盘中的文件名称被更改
        origin_unzip_path_obj.rename(new_unzip_path_obj)
        logger.info(f"{pdf_path_obj.stem}解析完成{new_unzip_path_obj}")

#读取markdown文件并保存到状态字典
        with open(new_unzip_path_obj, "r", encoding="utf-8") as f:
            md_content = f.read()
        return {
            "md_content": md_content,
            "md_path": str(new_unzip_path_obj)
        }


if __name__ == '__main__':
    node = NodePDFToMD()
    init_state = {
        "pdf_path": r"E:\AI大模型\第七阶段 掌柜智库\掌柜智库01\资料\05-设备手册汇总\doc\hak180产品安全手册.pdf",
        "local_dir" : r"C:\Users\Administrator\Desktop\gitee\my_project"
    }
    res = node(init_state)
    logger.info(res)









