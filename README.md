# python-alist-strm
将alist中的文件转换为strm导出

保持alist的目录结构，将alist某条路径下面的视频导出为strm，其他类型文件下载，已经导出过的路径会保存到数据库里面，对于下载错误的文件会保存到数据库里面，下次运行程序可以选择是否再次下载上传下载失败的文件。
# 使用方法
先使用python3 sql.py生成数据库，再填写main.py中的alist地址，下载位置，数据库位置，然后运行main.py即可。
