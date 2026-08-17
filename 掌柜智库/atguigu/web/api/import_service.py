import os
import shutil
import uuid
from pathlib import Path
from typing import Annotated

import fastapi
import uvicorn
from fastapi import FastAPI, UploadFile, File, BackgroundTasks
from starlette.middleware.cors import CORSMiddleware
from datetime import datetime

from atguigu.config.config import MinioConfig
from atguigu.import_process.main_graph import MainGraphRunner
from atguigu.tool.logger import logger
from atguigu.tool.minio_client_tool import create_minio_client
from atguigu.tool.task_utils import add_running_task, add_done_task, get_task_info, update_task_status, \
    TASK_STATUS_PROCESSING, TASK_STATUS_COMPLETED, TASK_STATUS_FAILED

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

#定义后台任务
def run_graph(
        task_id:str,
        local_file_path:str,
        local_dir:str
):
    #main_graph中途若失败,则抛出异常被base接收,再被这里的try接收,返回前端上传失败状态
    try:
        init_state = {
            "task_id":task_id,
            "local_file_path":local_file_path,
            "local_dir":local_dir
        }
        #更新总状态,执行main_graph之前总状态为process
        update_task_status(task_id,TASK_STATUS_PROCESSING)
        MainGraphRunner.create_runner(init_state)
        #更新总状态,执行main_graph之后总状态为complete
        update_task_status(task_id,TASK_STATUS_COMPLETED)
    except Exception as e:
        update_task_status(task_id,TASK_STATUS_FAILED)
        logger.error(f"任务ID为：{task_id}的文件上传失败，错误信息为：{e}")

# 接收上传文件的接口,将后端和前端串联,前端上传的文件就是流入graph的文件,构造main_graph所需参数即可
@app.post("/upload")
async def upload_api(
        bg_task: BackgroundTasks,
        file: Annotated[UploadFile, File(..., description="文件")]):
    # 1.生成task_id
    task_id= str(uuid.uuid4())

    #加上节点流转状态监控,这是上传文件的起始位置,添加进字典列表
    add_running_task(task_id,"upload_file")

    # 2.接收文件并保存到指定位置 输出目录下加上时间目录 strftime string format time 字符串格式化时间,把日期和时间对象转化为指定格式的字符串
    local_dir = fr"E:\AI大模型\第七阶段 掌柜智库\资料\05-设备手册汇总\output\{datetime.now().strftime('%Y-%m-%d')}"
    local_dir_obj = Path(local_dir)
    if not local_dir_obj.exists():
        os.makedirs(local_dir_obj, exist_ok=True)
    local_file_path = str(local_dir_obj / file.filename)

    # f.write(await file.read())先把对象读成二进制字节,再通过write写入文件
    # shutil.copyfileobj(file.file, f, 1024*1024)更合适,他会按照设置的缓冲区写入文件
    # 3.文件流写入指定路径
    with open(local_file_path,"wb") as f:
        # f.write(await file.read())
        shutil.copyfileobj(file.file, f, 1024*1024)
    logger.info(f"文件上传成功，保存路径为：{local_file_path}")

    #备份到minio
    minio_client = create_minio_client()
    minio_client.fput_object(
        bucket_name=MinioConfig.MINIO_BUCKET_NAME,
        object_name=f"back_up/{datetime.now().strftime('%Y-%m-%d')}/{task_id}/{file.filename}",
        file_path=local_file_path
    )
    logger.info(f"文件已备份到：{MinioConfig.MINIO_BUCKET_NAME}, object_name为：back_up/{datetime.now().strftime('%Y-%m-%d')}/{task_id}/{file.filename}")

    # 添加节点状态流转监控:这里文件上传结束,将其加入done字典列表,并从running字典列表中删除
    add_done_task(task_id, "upload_file")
    #文件保存和备份成功,接下俩就是开启后台任务,调用graph,进行存库一系列操作
    bg_task.add_task(run_graph,task_id,local_file_path,local_dir)



    return {"task_id":task_id}


#定义前端访问状态接口,所有信息都在里面,前端拿到包含所有信息的字典后进行页面展示
@app.get("/status/{task_id}")
async def get_status(task_id:Annotated[str,fastapi.Path(..., description="任务ID")]):
    return get_task_info(task_id)#这里面包含了所有的信息,根据前端轮询发送请求,可以动态获得里面不同的信息,从而实现前端和后端的动态交互显示









if __name__ == '__main__':
    uvicorn.run(
        app=app,
        host="0.0.0.0",
        port=8000
    )