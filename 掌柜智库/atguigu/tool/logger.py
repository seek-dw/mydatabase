"""
创建日志显示系统
"""
import logging

import colorlog

#获取日志对象
logger = logging.getLogger()

#设置日志级别
logger.setLevel(logging.DEBUG)

#设置日志输出地点
handler = colorlog.StreamHandler()#默认采用stderr输出,不用stdout,日志不是正常输出

#当终端重定向输出的时候,logging.info()是不会被重定向,如果改用了stdout模式,则会重定向

#设置日志输出格式
if not logger.handlers:
    handler.setFormatter(colorlog.ColoredFormatter(
        #设置完整的日志格式
        fmt = '%(log_color)s%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s',
        #设置日志时间格式
        datefmt = '%Y-%m-%d %H:%M:%S',
        #设置日志颜色
        log_colors = {
            'DEBUG': 'cyan',
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'bold_red',
        }
    ))

    #添加日志输出地点
    logger.addHandler(handler)

if __name__ == '__main__':
    logger.debug('This is a debug message')
    logger.info('This is an info message')
    logger.warning('This is a warning message')
    logger.error('This is an error message')
    logger.critical('This is a critical message')