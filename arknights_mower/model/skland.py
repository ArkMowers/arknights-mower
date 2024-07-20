from pydantic import BaseModel


class SKLandConfig(BaseModel):
    """
    SKLand 配置
    """

    account: str = ""
    "账号"
    isCheck: bool = True
    "是否启用"
    sign_in_official: bool = True
    "是否官服签到（暂没用）"
    sign_in_bilibili: bool = True
    "是否b站签到（暂没用）"
    cultivate_select: bool = True
    """
    签到服务器选择
    
    true 为官服
    false 为b服
    TODO: 是否改为枚举？
    """
