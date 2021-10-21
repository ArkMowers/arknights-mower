from .model import OcrHandle
from .ocrspace import API, Language
from ..utils.config import OCR_APIKEY

ocrhandle = OcrHandle()
ocronline = API(api_key=OCR_APIKEY, language=Language.Chinese_Simplified)
