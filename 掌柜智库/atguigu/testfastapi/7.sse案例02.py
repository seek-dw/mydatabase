# 案例2 使用post请求
# 1、前端发请求传递一个query，再传递一个session_id  两个参数到后端，使用请求体参数传递
# 2、后端写一个接口获取这两个参数，并返回给前端收到的消息，并启动task造消息放入异步队列
# 3、前端订阅sse请求
# 4、服务端需要写sse回复接口，从task当中获取自己的队列，从队列当中一个一个yield球
"""
实现思路:

前端要实现以下功能:
    1.携带请求体参数对后端发送请求
    2.订阅sse请求,将sse的返回数据显示在前端页面上
后端的接口功能实现:
    1.接收前端的请求体参数,并且制作后台任务,开始处理前端发送请求的目的
    2.接收sse订阅请求,定义生成器函数并实现返回StreamResponse流式返回
"""
import asyncio
import time
from asyncio import Queue
from typing import Annotated

import uvicorn
from fastapi import FastAPI, Body, BackgroundTasks
from fastapi.params import Path
from pydantic import BaseModel, Field
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import StreamingResponse

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

queue_dict ={}

async def sse02_task(query,session_id):
    while not queue_dict.get(session_id):
        queue_dict[session_id]=Queue() #采用异步队列,所有异步操作都要加上await
    dq = queue_dict.get(session_id)
    await dq.put({"msg":"1"})
    await dq.put({"msg":"2"})
    await dq.put({"msg":"3"})
    await dq.put({"msg":"4"})
    await dq.put({"msg":"5"})
    await dq.put({"msg":"6"})
    print(dq)

#请求体参数,所以构建BaseModel类
#pydantic里面定义数据类型用Field
class Sse02params(BaseModel):
    query: Annotated[str,Field(...,description="查询内容")]
    session_id: Annotated[str,Field(...,description="会话ID")]

#定义后台任务接口，接收前端请求体参数，并返回给前端收到的消息
@app.post("/sse02")
async def sse02(
        bg_task: BackgroundTasks,
        sse_params: Annotated[Sse02params, Body(..., description="请求体参数")]):
    bg_task.add_task(sse02_task, sse_params.query, sse_params.session_id)
    return {"msg":"收到,开始查询信息造消息"}

#生成器函数
async def generator_func(session_id):
    while not queue_dict.get(session_id):
        await asyncio.sleep(1)
    dq = queue_dict.get(session_id)
    while True:
        res = await dq.get()
        await asyncio.sleep(1)
        yield f"data:{res}\n\n"
        if res is None:
            break



@app.get("/stream/{session_id}")
async def sse(session_id:Annotated[str,Path(...,description="会话ID")]):
    return StreamingResponse(generator_func(session_id),
                             media_type="text/event-stream")








if __name__ == '__main__':
    uvicorn.run(
        app=app,
        host="0.0.0.0",
        port=8000,

    )