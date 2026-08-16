"""
如果一个接口接收的是一个后台任务对象
    1.那么这个接口就变成了一个后台任务接口
    2.可以在这个接口里面添加任务,任务相当于一个函数，这个函数会在后台运行
    3.任务函数可以有参数,参数的类型可以是int,str,bool等
"""
import uvicorn
from fastapi import FastAPI, BackgroundTasks

app = FastAPI()

def print2():
    for i in range(5):
        print("helloword")


@app.get("/testbackgroundtask")
def testbackgroundtask(bgt:BackgroundTasks):
    bgt.add_task(print2)
    return {"已收到请求,已经开启后台任务"}

if __name__ == '__main__':
    uvicorn.run(
        app = app,
        host = "0.0.0.0",
        port = 8000
    )