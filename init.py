import os

# 创建目录，如果它们不存在
os.makedirs("cache/config", exist_ok=True)
os.makedirs("config", exist_ok=True)
os.makedirs("log", exist_ok=True)
os.makedirs("userLog", exist_ok=True)
