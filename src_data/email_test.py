import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from notification import NotificationService

# 初始化通知服务
notifier = NotificationService()

# 发送测试消息
success = notifier.send_to_email("这是来自 StockBot 的测试邮件！")

if success:
    print("测试邮件发送成功！")
else:
    print("测试邮件发送失败，请检查配置或日志。")