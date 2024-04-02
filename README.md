# 指引  
服务器端.py: Server主进程  
客户端.py：客户端主进程  
default.py：默认用户代码  
  
# 安装&测试库  
下载requirements.txt和init.py，保证它们在同一目录下  
执行init.py  
输出在控制台  
  
# 更改服务器端口配置  
打开服务器端.py  
拉到最下面，直到看到  
asyncio.run(main(port=11001))  
将port更改为你想要的  
  
# 更改客户端连接的服务器地址  
在最上面，直到看到  
uri = "ws://v1an.xyz:11001"  
将uri更改为你的websocket地址，记得加上端口号  
  
# 开启服务器  
下载服务器端.py，default.py和map.txt，保证它们处于同一目录下  
执行服务器端.py  
  
# 开启客户端  
下载客户端.py，image文件夹  
执行客户端.py  
  
