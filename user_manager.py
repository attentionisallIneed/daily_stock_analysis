# -*- coding: utf-8 -*-
import json
import os
import logging
from typing import List, Set
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class UserConfig:
    name: str
    email: str
    stocks: List[str]

class UserManager:
    """
    用户管理模块
    负责从 users.json 加载多用户配置，实现分组推送
    """
    def __init__(self, config_path: str = "users.json"):
        # 优先在当前目录查找，其次在 data 目录查找
        if not os.path.exists(config_path) and os.path.exists(os.path.join("data", config_path)):
            config_path = os.path.join("data", config_path)
            
        self.config_path = config_path
        self.users: List[UserConfig] = []
        self._load_users()

    def _load_users(self):
        """加载用户配置"""
        if not os.path.exists(self.config_path):
            logger.debug(f"用户配置文件 {self.config_path} 不存在，将使用单用户模式")
            return

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                # 支持 {"users": [...]} 或 [...] 两种格式
                if isinstance(data, dict) and "users" in data:
                    user_list = data["users"]
                elif isinstance(data, list):
                    user_list = data
                else:
                    logger.warning(f"users.json 格式不正确，应为列表或包含 'users' 键的字典")
                    return

                for u in user_list:
                    # 验证必要字段
                    email = u.get("email")
                    stocks = u.get("stocks", [])
                    
                    if email and stocks:
                        # 确保股票代码是字符串
                        clean_stocks = [str(s).strip() for s in stocks if str(s).strip()]
                        self.users.append(UserConfig(
                            name=u.get("name", email.split('@')[0]),
                            email=email,
                            stocks=clean_stocks
                        ))
            
            if self.users:
                logger.info(f"成功加载 {len(self.users)} 个特定的用户配置")
        except Exception as e:
            logger.error(f"加载 users.json 失败: {e}")

    def get_all_stocks(self) -> Set[str]:
        """获取所有用户关注的股票集合（去重后）"""
        stocks = set()
        for user in self.users:
            stocks.update(user.stocks)
        return stocks

    def get_users(self) -> List[UserConfig]:
        """获取所有用户列表"""
        return self.users
    
    def has_users(self) -> bool:
        """是否有有效的多用户配置"""
        return len(self.users) > 0
