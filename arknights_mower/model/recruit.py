from pydantic import BaseModel


class RecruitConfig(BaseModel):
    """
    招募配置
    """

    recruit_enable: bool = True
    "是否进行公开招募"

    recruit_robot: bool = True
    "公招是否招募小车"

    recruitment_time: bool = False
    """
    公招时间

    true: 7:40
    false: 9:00
    TODO: 是否改为 TimeDelta?
    """

    recruitment_permit: int = 30
    "招募三星干员公招券阈值"

    recruit_gap: float = 9
    """
    公招间隔

    单位为小时，可以为小数
    """

    recruit_auto_5: bool = True
    "是否自动进行五星招募"

    recruit_auto_only_5: bool = False
    "五星词条组合唯一时自动选择"

    recruit_email_enable: bool = True
    "是否启用公招邮件通知"
