import json

# 读取 JSON 文件
with open('data.json', 'r') as file:
    data = json.load(file)

# 打印文件内容
print("Data from data.json:")
print(data)