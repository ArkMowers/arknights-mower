"""办公室、训练室与回收站的本地布局约束。"""

RIGHT_SIDE_ROOM_ORDERS = (
    ("contact", "train", "recycle"),
    ("train", "contact", "recycle"),
    ("train", "recycle", "contact"),
)
