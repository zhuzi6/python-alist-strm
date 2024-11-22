import sqlite3

# 指定数据库文件的路径
db_path = r"/root/STRM/processed_paths.db"

# 连接到数据库文件（如果文件不存在，将自动创建）
conn = sqlite3.connect(db_path)

# 创建游标对象
cursor = conn.cursor()

# 创建数据表 processed_paths，如果表已存在，不会重复创建
cursor.execute("""
CREATE TABLE IF NOT EXISTS processed_paths (
    path TEXT PRIMARY KEY  -- 路径是唯一的
)
""")

# 提交事务
conn.commit()

# 关闭连接
conn.close()

print(f"数据库已创建，路径: {db_path}")