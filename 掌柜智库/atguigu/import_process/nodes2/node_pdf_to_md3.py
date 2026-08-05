import shutil
import time
from pathlib import Path

from atguigu.config.config import MinerUConfig
from atguigu.import_process.base import NodeBase
from atguigu.import_process.state import ImportGraphState
from atguigu.tool.logger import logger
#第三遍:
"""
1.判断pdf路径,pdf目录正确保证有pdf文件
2.向mineru服务器发送请求post
3.解析服务器的请求获取batch id,并将本地的路径上传至服务器分配的urls
4.根据batch_id再次发送get请求轮询,获得压缩包url地址
5.再次发送get请求下载压缩包
"""
class NodePDFToMD(NodeBase):
    """
    PDF 转 Markdown 节点：PDF结构化解析
    """
    name = "node_pdf_to_md"

    def process(self,state:ImportGraphState):
        pdf_path = state.get("pdf_path", "")
        if not pdf_path:
            logger.error("路径错误")
            raise Exception("该路径不存在")
        pdf_path_obj = Path(pdf_path)
        if not pdf_path_obj.exists():
            logger.error("路径错误")
            raise Exception("路径错误,请上传正确路径")

        import requests

        token = MinerUConfig.MINERU_API_KEY
        url = "https://mineru.net/api/v4/file-urls/batch"
        header = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        data = {
            "files": [
                {"name": f"{pdf_path_obj.stem}.pdf", "data_id": "abcd"}
            ],
            "model_version": "vlm"
        }
        file_path = [f"{pdf_path}"]
        response = requests.post(url, headers=header, json=data)
        if response.status_code == 200:
            result = response.json()
            if result["code"] == 0:
                batch_id = result["data"]["batch_id"]
                urls = result["data"]["file_urls"]
                for i in range(0, len(urls)):
                    with open(file_path[i], 'rb') as f:
                        res_upload = requests.put(urls[i], data=f)
                        if res_upload.status_code == 200:
                            print(f"{urls[i]} upload success")
                        else:
                            print(f"{urls[i]} upload failed")

        import requests

        token = MinerUConfig.MINERU_API_KEY
        batch_id = batch_id
        url = f"https://mineru.net/api/v4/extract-results/batch/{batch_id}"
        header = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        use_time = 0
        total_time =30
        while True:
            start = time.time()
            try:
                res = requests.get(url, headers=header)
                if res.status_code !=200:
                    logger.error("向服务器发送请求失败")
                    raise Exception("向服务器发送请求失败")
                result = res.json()
                if result['code'] != 0:
                    logger.error("向服务器发送请求,数据返回失败")
                    raise Exception("向服务器发送请求,数据返回失败")
                extract_result = result["data"]["extract_result"][0]
                if extract_result["state"] != "done":
                    logger.error("文件处理中")
                    raise Exception("文件处理中,请稍后")
                md_zip_url = extract_result.get("full_zip_url")
                print(md_zip_url)
                break
            except Exception as e:
                use_time += time.time() - start
                if use_time > total_time:
                    raise Exception("处理超时")
                continue

        md_zip = requests.get(md_zip_url)
        if md_zip.status_code != 200:
            logger.error("向服务器发送请求失败")
            raise Exception("向服务器发送请求失败")
        md_zip_content = md_zip.content
        md_zip_path = pdf_path_obj.parent / f"{pdf_path_obj.stem}.zip"
        with open(md_zip_path, "wb") as f:
            f.write(md_zip_content)

        import zipfile
        md_zip_content = zipfile.ZipFile(md_zip_path)
        unzip_path = pdf_path_obj.parent / f"{pdf_path_obj.stem}"
        if unzip_path.exists():
            shutil.rmtree(unzip_path)
        md_zip_content.extractall(unzip_path)

        origin_unzip_md_file = unzip_path / "full.md"
        new_unzip_md_file = origin_unzip_md_file.with_name(f"{pdf_path_obj.stem}.md")
        origin_unzip_md_file.rename(new_unzip_md_file)

        return {
            "md_path": new_unzip_md_file
        }



if __name__ == '__main__':
    node = NodePDFToMD()
    init_state = {
        "pdf_path": r"E:\AI大模型\第七阶段 掌柜智库\资料\05-设备手册汇总\doc\hak180产品安全手册.pdf"
    }
    res = node(init_state)
    logger.info(res)