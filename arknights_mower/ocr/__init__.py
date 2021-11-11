from .model import OcrHandle
from .ocrspace import API, Language
from ..utils import config
from ..utils.log import logger
from ..data.ocr import ocr_error

ocrhandle = OcrHandle()
ocronline = API(api_key=config.OCR_APIKEY, language=Language.Chinese_Simplified)


def ocr_rectify(img, pre, valid, text=''):
    """
    调用在线 OCR 校正本地 OCR 得到的错误结果，并返回校正后的识别结果
    若在线 OCR 依旧无法正确识别则返回 None
    
    :param img: numpy.array, 图像
    :param pre: (str, tuple), 本地 OCR 得到的错误结果，包括字符串和范围
    :param valid: list[str], 期望得到的识别结果
    :param text: str, 指定 log 信息前缀

    :return res: str | None, 识别的结果
    """
    logger.warning(f'{text}识别异常：正在调用在线 OCR 处理异常结果……')
    pre_res = pre[1]
    res = ocronline.predict(img, pre[2])
    if res is None or res == pre_res:
        logger.warning(
            f'{text}识别异常：{pre_res} 为不存在的数据，请报告至 https://github.com/Konano/arknights-mower/issues')
    elif res not in valid:
        logger.warning(
            f'{text}识别异常：{pre_res} 和 {res} 均为不存在的数据，请报告至 https://github.com/Konano/arknights-mower/issues')
    else:
        logger.warning(
            f'{text}识别异常：{pre_res} 应为 {res}，请报告至 https://github.com/Konano/arknights-mower/issues')
        ocr_error[pre_res] = res
        pre_res = res
    return pre_res
