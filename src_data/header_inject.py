import requests
import time

# 模拟真实的浏览器 Header
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://data.eastmoney.com/",
    "Accept-Language": "zh-CN,zh;q=0.9"
}

# 尝试访问一个数据接口（这是 Akshare 底层可能调用的接口之一）
url = "https://push2.eastmoney.com/api/qt/clist/get" 
# 这里只是示例参数，目的是测试连接
params = {
    "pn": "1", "pz": "20", "po": "1", "np": "1", 
    "ut": "bd1d9ddb04089700cf9c27f6f7426281", "fltt": "2", "invt": "2",
    "fid": "f3", "fs": "m:0+t:6,m:0+t:80", "fields": "f1,f2,f3,f4,f12,f13,f14"
}

try:
    print("正在尝试连接数据接口...")
    response = requests.get(url, headers=headers, params=params, timeout=10)
    print(f"状态码: {response.status_code}")
    if response.status_code == 200:
        print("数据获取成功（前50字符）:", response.text[:50])
    else:
        print("被拦截或报错")
except Exception as e:
    print(f"连接失败: {e}")