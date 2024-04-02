import os

def install_requirements(requirements):
    # 安装每个库
    message = ["Install info:"]
    for requirement in requirements:
        try:
            requirement = requirement.strip()  # 删除前后的空格和换行符
            os.system(f"pip3 install {requirement} -i https://mirrors.aliyun.com/pypi/simple/")

            message.append(f"{requirement} √")
        except Exception as e:
            message.append(f"{requirement} ×, reason: {e}")
    for m in message:
        print(m)

def test_requirements(requirements):
    # 测试每个库
    message = ["Import info:"]
    for requirement in requirements:
        try:
            requirement = requirement.strip()  # 删除前后的空格和换行符
            exec(f"import {requirement}")

            message.append(f"{requirement} √")
        except Exception as e:
            message.append(f"{requirement} ×, reason: {e}")
    for m in message:
        print(m)

if __name__ == "__main__":
    with open('requirements.txt', 'r') as file:
        requirements = file.readlines()
    install_requirements(requirements)
    test_requirements(requirements)

# 创建目录，如果它们不存在
os.makedirs("cache/config", exist_ok=True)
os.makedirs("config", exist_ok=True)
os.makedirs("log", exist_ok=True)
os.makedirs("userLog", exist_ok=True)
print("mkdir success")
