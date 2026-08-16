from pathlib import Path

import uvicorn
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import FileResponse
from starlette.staticfiles import StaticFiles

app = FastAPI()

BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "uploads"


#挂载静态文件
    # 挂载和不挂载的区别
    # 当前端上传图片给后端,后端保存后,不挂载就是服务器电脑上的一个文件
    # 挂载之后相当于告诉fastapi,凡是访问/uploads/xxx的请求,就去STATIC_DIR目录下找xxx文件返回给前端
    # 通俗就是将磁盘的文件暴露到你指定的某个路径下的请求当中
#挂载:第一个参数是暴露的路径,第二个参数是静态文件存放的目录,第三个参数是这个挂载点的名字
app.mount("/static",StaticFiles(directory=str(STATIC_DIR)), name="static")


app.add_middleware(
    CORSMiddleware,
    #允许谁访问
    allow_origins=["*"],
    #允许跨域请求使用什么方法 get,put,post,delete
    allow_methods=["*"],
    #允许跨域请求携带什么请求头,基本请求头全部放行*
    allow_headers=["*"],
    #是否允许跨域请求携带凭证信息
    allow_credentials=True,
    #允许前端读取什么响应头
    expose_headers=["*"],
    #预检请求缓存时间,单位秒,防止多次连续请求,每次都要进行预检
    max_age=86400
)


# 测试前后端不分离,返回写好的html页面
# 浏览器访问localhost:8000/访问到index.html
# 这个时候index.html的ip端口和后端相同,在发送请求给/test_cors的时候,不跨域,所以可以成功接收到返回的数据
# 如果直接用浏览器打开html,浏览器会为其自动分配ip,和后端不一致,即跨域,跨域需要加入跨域中间件,加入后允许跨域
@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")

@app.get("/test_cors")
def test_cors():
    return {"message":"cors is success"}


if __name__ == '__main__':

    uvicorn.run(app,host = "0.0.0.0",port = 8000)