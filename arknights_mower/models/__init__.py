import lzma
import pickle

from arknights_mower import __rootdir__

with lzma.open(f"{__rootdir__}/models/avatar.pkl", "rb") as f:
    avatar = pickle.load(f)


with lzma.open(f"{__rootdir__}/models/secret_front.pkl", "rb") as f:
    secret_front = pickle.load(f)


with lzma.open(f"{__rootdir__}/models/navigation.pkl", "rb") as f:
    navigation = pickle.load(f)

with lzma.open(f"{__rootdir__}/models/riic_base_digits.pkl", "rb") as f:
    riic_base_digits = pickle.load(f)

with lzma.open(f"{__rootdir__}/models/noto_sans.pkl", "rb") as f:
    noto_sans = pickle.load(f)

with lzma.open(f"{__rootdir__}/models/shop.pkl", "rb") as f:
    shop = pickle.load(f)
