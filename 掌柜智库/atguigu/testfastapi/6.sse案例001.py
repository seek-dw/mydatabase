# 案例1
# 	1、客户前端发ajax请求要发邮件并携带session_id，服务端直接回复收到，制造邮件开始
# 	2、服务端就开始执行backgroundtasks当中造邮件的函数，造的邮件全部放在队列当中
# 	3、客户端想直接拿到造的邮件内容，造一个拿一个，那么客户端需要去发送订阅sse请求
# 	4、服务端需要写sse回复接口，流式返回，流式返回就是把一个生成器对象返回
# 		生成器函数当中就是从queue_dict当中获取自己session_id的队列，从队列当中一个一个yield球
# 注意：每个session_id对应自己的邮件队列

"""
    实现思路:
    1.先写前端,至少包含发送请求按钮,按钮对接的脚本里面要携带session_id参数
    2.写后端,写一个制造邮件的函数,这个函数得用队列存放邮件
    3.再写一个后台任务的接口,把函数添加到后台任务接口里面去,返回"收到,制造邮件开始"
    4.再补充前端,需要写一个sse的请求,建立sse连接
    5.再补充后端的制造邮件必须是一个生成器函数,然后把生成器对象添加到后台任务当中实现流式返回
前端
 ↓
/sse01?session_id=123
 ↓
FastAPI
 ↓
BackgroundTasks
 ↓
make_email()
 ↓
生成邮件
 ↓
q.put(邮件)

前端
 ↓
/stream?session_id=123
 ↓
FastAPI
 ↓
找到 session_id=123 对应的 Queue
 ↓
q.get()
 ↓
yield
 ↓
StreamingResponse
 ↓
SSE
 ↓
前端实时收到
"""
import time
from queue import Queue
from typing import Annotated
import uvicorn
from fastapi import FastAPI, BackgroundTasks
from fastapi.params import Query
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import StreamingResponse

app = FastAPI()


queue_dict = {}
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


def make_email(session_id:Annotated[str,Query(...,description="会话id")]):
    #如果队列字典中没有该会话的队列,创建
    if not queue_dict.get(session_id):
        queue_dict[session_id] = Queue()
    #拿到该会话的队列
    q = queue_dict.get(session_id)
    #往队列中放入邮件数据
    q.put("第一封邮件")
    q.put("第二封邮件")
    q.put("第三封邮件")
    q.put("第四封邮件")
    q.put("第五封邮件")
    q.put("第六封邮件")
    q.put(None)

#创建后台任务接口,作用是前端发送请求后立马给前端返回响应数据并同时在后台开始制造邮件并存储
@app.get("/sse01")
def sse01(
        bgt:BackgroundTasks,
        session_id:Annotated[str,Query(...,description="会话id")]
):
    bgt.add_task(make_email,session_id = session_id) #左边session_id是make_email的参数,右边是当前接口的参数
    return {"message": "收到，立马给您造邮件存储"}


#当前端想要后端主动推送数据的时候,订阅该接口即可
#创建sse接口,作用是从储存好的数据当中取出数据主动发送给前端
@app.get("/stream")
def stream(session_id:Annotated[str,Query(...,description="会话id")]):
    # 创建一个生成器函数
    def get_email():
        #这里不能改成if,while代表每2s都要检查一次是否出现该会话的队列,如果改成if则只检查一次
        while not queue_dict.get(session_id):
            time.sleep(2)
        #取出所有邮件
        q = queue_dict.get(session_id)
        while True:
            #先进先出单向队列,put队首-队尾放入,get队首-队尾取出
            email = q.get()
            yield f"data:{email}\n\n" #固定的sse推送数据格式只有这样写前端页面才会显示
            if email is None:
                break
            time.sleep(1)
    return StreamingResponse(get_email(),media_type="text/event-stream")








if __name__ == '__main__':
    uvicorn.run(
        app = app,
        host = "0.0.0.0",
        port = 8000,

    )