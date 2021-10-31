from .model import OcrHandle
from .ocrspace import API, Language
from ..utils.log import logger
from ..utils.config import OCR_APIKEY
from ..data.ocr import ocr_error

ocrhandle = OcrHandle()
ocronline = API(api_key=OCR_APIKEY, language=Language.Chinese_Simplified)


def ocr_amend(img, pre, dataset, text=''):
    logger.warning(f'{text}识别异常：正在调用在线识别处理异常结果……')
    pre_res = pre[1]
    res = ocronline.predict(img, pre[2])
    if res is None or res == pre_res:
        logger.warning(
            f'{text}识别异常：{pre_res} 为不存在的数据，请报告至 https://github.com/Konano/arknights-mower/issues')
    elif res not in dataset:
        logger.warning(
            f'{text}识别异常：{pre_res} 和 {res} 均为不存在的数据，请报告至 https://github.com/Konano/arknights-mower/issues')
    else:
        logger.warning(
            f'{text}识别异常：{pre_res} 应为 {res}，请报告至 https://github.com/Konano/arknights-mower/issues')
        ocr_error[pre_res] = res
        pre_res = res
    return pre_res
