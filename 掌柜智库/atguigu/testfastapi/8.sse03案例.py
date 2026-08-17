# 案例2 使用post请求
# 1、前端发请求传递一个query，再传递一个session_id  两个参数到后端，使用请求体参数传递
# 2、后端写一个接口获取这两个参数，并返回给前端收到的消息，并启动task造消息放入异步队列
# 3、前端订阅sse请求
# 4、服务端需要写sse回复接口，从task当中获取自己的队列，从队列当中一个一个yield球
"""
实现思路:

该案例在002案例的基础上进行修改
    主要修改:
        从推送数据变成了推送事件
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
    CORSMiddleware,#type:ignore
    allow_origins=["*"],#type:ignore
    allow_credentials=True,#type:ignore
    allow_methods=["*"],#type:ignore
    allow_headers=["*"],#type:ignore
)

queue_dict ={}

async def sse03_task(query,session_id):
    while not queue_dict.get(session_id):
        queue_dict[session_id]=Queue() #采用异步队列,所有异步操作都要加上await
    dq = queue_dict.get(session_id)
    #这样写的目的就是为了前端页面的时候使用自定义事件,名字可以任意取,不需要收到系统事件的约束
    #将最基础的数据替换为字典,字典内键为事件，值为自定义的事件名,数据同样使用键值对进行存储
    await dq.put({"event":"process","data":"数据1"})
    await dq.put({"event":"process","data":"数据2"})
    await dq.put({"event":"process","data":"数据3"})
    await dq.put({"event":"process","data":"数据4"})
    await dq.put({"event":"process","data":"数据5"})
    await dq.put({"event":"final","data":"结束"})
    # await dq.put({"msg":"1"})
    # await dq.put({"msg":"2"})
    # await dq.put({"msg":"3"})
    # await dq.put({"msg":"4"})
    # await dq.put({"msg":"5"})
    # await dq.put({"msg":"6"})
    print(dq)

#请求体参数,所以构建BaseModel类
#pydantic里面定义数据类型用Field
class Sse02params(BaseModel):
    query: Annotated[str,Field(...,description="查询内容")]
    session_id: Annotated[str,Field(...,description="会话ID")]

#定义后台任务接口，接收前端请求体参数，并返回给前端收到的消息
@app.post("/sse03")
async def sse03(
        bg_task: BackgroundTasks,
        sse_params: Annotated[Sse02params, Body(..., description="请求体参数")]):
    bg_task.add_task(sse03_task, sse_params.query, sse_params.session_id)
    return {"msg":"收到,开始查询信息造消息"}

#生成器函数
"""
sse订阅的时候使用EventSource事件源对象创建,所以sse推送的数据都是一个个事件
f"data:{数据}\n\n"
第一个\n代表换行 第二个\n代表事件结束
f"event:{事件名}\n"
f"data:{数据}\n\n"
这两行代表一个事件,第一个event就是给这个事件其名字了,最核心的还是data,一个sse事件可以包含多行
"""
async def generator_func(session_id):
    while not queue_dict.get(session_id):
        await asyncio.sleep(1)
    dq = queue_dict.get(session_id)
    while True:
        #此时res变成了一个装有事件和数据的字典
        try:
            res = await dq.get()
            await asyncio.sleep(1)
            event = res.get("event")
            data = res.get("data")
            yield f"event:{event}\n"
            yield f"data:{data}\n\n"
            if event is "final":
                break
        except Exception as e:
            yield f"event: error\n"
            yield f"data: {e}\n\n"


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