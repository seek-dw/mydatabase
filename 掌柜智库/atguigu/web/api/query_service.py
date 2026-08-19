import json
import uuid
from typing import Annotated

import uvicorn
from fastapi import FastAPI, BackgroundTasks
from fastapi.params import Path, Body
from pydantic import BaseModel, Field
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import StreamingResponse

from atguigu.query_process.main_graph import MainGraphRunner
from atguigu.tool.mongo_client_tool import get_recent_history_list, clear_history
from atguigu.tool.task_utils import get_data, create_queue, put_data, get_task_info, TASK_STATUS_PROCESSING, \
    TASK_STATUS_COMPLETED, TASK_STATUS_FAILED, update_task_status

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# api of 1
#心脏跳动检测接口,也就是测试前后端是否已经成功连接的接口
   #在前端页面的显示是"API未连接" | "API已连接"
@app.get("/health")
async def check_heart():
    return {"message": "API已连接"}

# api of 2
#前端页面显示历史记录的接口,前端请求携带了session_id,所以此处使用路径参数进行接收
@app.get("/history/{session_id}")
async def send_history(session_id:Annotated[str,Path(...,description="会话ID")]):


    #直接通过定义好的方法拿出历史记录返回给前端
    history_list =get_recent_history_list(session_id,limit = 10)
    history_list = sorted(history_list, key=lambda x: x["ts"])
    #历史记录里面的id是一个对象,这里要把id转为字符串
    history_list = [{
        "_id":str(history["_id"]),
        "session_id":history.get("session_id"),
        "role":history.get("role"),
        "text":history.get("text"),
        "rewritten_query":history.get("rewritten_query"),
        "item_names":history.get("item_names"),
        "ts":history.get("ts")
    }
        for history in history_list]
    # 因为先写的前端,后写的后端,所以这里返回的键一定要和前端拿值的键一样,"items"
    return {"items": history_list}

# api of 3
# 通过前端的请求可以看出前端的判断是只要请求的ok存在,就会执行前端的删除历史记录的函数,所以只要让前端的请求成功即可,返回无所谓了
@app.delete("/history/{session_id}")
async def delete_history(session_id:Annotated[str,Path(...,description="会话ID")]):
    clear_history(session_id=session_id)
    return {"message": "历史记录删除成功"}

# api of 4
# 前端的输入框接口对接，也就是用户输入问题的接口
# 通过前端测试发现请求固定路径为query,携带参数为请求体参数 {query,session_id}

class BodyParams(BaseModel):
    query:Annotated[str,Field(...,description="用户输入的问题")]
    session_id:Annotated[str,Field(...,description="会话ID")]


def ask_question_search(task_id,query, session_id):

    create_queue(task_id) #调用创建队列方法,队列字典里面已经有队列了,无需变量接收
    try:
        init_state = {
            "task_id": task_id,
            "original_query": query,
            "session_id": session_id
        }
        update_task_status(task_id, TASK_STATUS_PROCESSING)
        put_data(task_id,event = "progress",data = get_task_info(task_id))
        MainGraphRunner.create_and_run(init_state)
        update_task_status(task_id, TASK_STATUS_COMPLETED)
        put_data(task_id,event = "progress",data = get_task_info(task_id))
    except Exception as e:
        update_task_status(task_id, TASK_STATUS_FAILED)
        put_data(task_id,event = "error",data = get_task_info(task_id))
        raise e



@app.post("/query")
async def ask_question(
        bgt:BackgroundTasks,
        body:Annotated[BodyParams, Body(..., description="请求体参数")]):
    #创建任务id
    task_id = str(uuid.uuid4()) #一定要加str不然就是个对象,前端根本拿不到任何东西
    #添加后台任务
    bgt.add_task(ask_question_search, task_id, body.query, body.session_id)
    return {
        "task_id":task_id,
        "query":body.query,
        "session_id":body.session_id
    }


# api of 5
# sse接口,通过向队列添加数据实现状态的流转存储,然后通过sse一个个利用队列的特性取出来推送给前端
@app.get("/stream/{task_id}")
async def stream(task_id:Annotated[str,Path(...,description="任务ID")]):
    #定义生成器函数,从队列中取数据并且一个个推送
    def generator_func(task_id):
        #这里不需要再次判断队列字典里面是否存在队列,因为在get_data里面已经封装了
        while True:
            item = get_data(task_id)
            # 推送事件和数据给前端
            yield f"event: {item.get("event","")}\n"
            yield f"data: {json.dumps(item.get("data",""),ensure_ascii=False)}\n\n" #这是歌状态列表,要转json字符串

    return StreamingResponse(generator_func(task_id), media_type="text/event-stream")



if __name__ == '__main__':
    uvicorn.run(
        app = app,
        host = '0.0.0.0',
        port = 8001
    )