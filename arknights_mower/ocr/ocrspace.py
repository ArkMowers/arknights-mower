import base64
import traceback

import cv2
import numpy
import requests

from ..utils.log import logger
from ..utils.recognize import RecognizeError
from .utils import fix


class Language:
    Arabic = 'ara'
    Bulgarian = 'bul'
    Chinese_Simplified = 'chs'
    Chinese_Traditional = 'cht'
    Croatian = 'hrv'
    Danish = 'dan'
    Dutch = 'dut'
    English = 'eng'
    Finnish = 'fin'
    French = 'fre'
    German = 'ger'
    Greek = 'gre'
    Hungarian = 'hun'
    Korean = 'kor'
    Italian = 'ita'
    Japanese = 'jpn'
    Norwegian = 'nor'
    Polish = 'pol'
    Portuguese = 'por'
    Russian = 'rus'
    Slovenian = 'slv'
    Spanish = 'spa'
    Swedish = 'swe'
    Turkish = 'tur'


class API:
    def __init__(
        self,
        endpoint='https://api.ocr.space/parse/image',
        api_key='helloworld',
        language=Language.Chinese_Simplified,
        **kwargs,
    ):
        """
        :param endpoint: API endpoint to contact
        :param api_key: API key string
        :param language: document language
        :param **kwargs: other settings to API
        """
        self.timeout = (5, 10)
        self.endpoint = endpoint
        self.payload = {
            'isOverlayRequired': True,
            'apikey': api_key,
            'language': language,
            **kwargs
        }

    def _parse(self, raw):
        logger.debug(raw)
        if type(raw) == str:
            raise RecognizeError(raw)
        if raw['IsErroredOnProcessing']:
            raise RecognizeError(raw['ErrorMessage'][0])
        if raw['ParsedResults'][0].get('TextOverlay') is None:
            raise RecognizeError('No Result')
        # ret = []
        # for x in raw['ParsedResults'][0]['TextOverlay']['Lines']:
        #     left, right, up, down = 1e30, 0, 1e30, 0
        #     for w in x['Words']:
        #         left = min(left, w['Left'])
        #         right = max(right, w['Left'] + w['Width'])
        #         up = min(up, w['Top'])
        #         down = max(down, w['Top'] + w['Height'])
        #     ret.append([x['LineText'], [(left + right) / 2, (up + down) / 2]])
        # return ret
        ret = [x['LineText']
               for x in raw['ParsedResults'][0]['TextOverlay']['Lines']]
        return ret

    def ocr_file(self, fp):
        """
        Process image from a local path.
        :param fp: A path or pointer to your file
        :return: Result in JSON format
        """
        with (open(fp, 'rb') if type(fp) == str else fp) as f:
            r = requests.post(
                self.endpoint,
                files={'filename': f},
                data=self.payload,
                timeout=self.timeout,
            )
        return self._parse(r.json())

    def ocr_url(self, url):
        """
        Process an image at a given URL.
        :param url: Image url
        :return: Result in JSON format.
        """
        data = self.payload
        data['url'] = url
        r = requests.post(
            self.endpoint,
            data=data,
            timeout=self.timeout,
        )
        return self._parse(r.json())

    def ocr_base64(self, base64image):
        """
        Process an image given as base64.
        :param base64image: Image represented as Base64
        :return: Result in JSON format.
        """
        data = self.payload
        data['base64Image'] = base64image
        r = requests.post(
            self.endpoint,
            data=data,
            timeout=self.timeout,
        )
        return self._parse(r.json())

    def ocr_image(self, image: numpy.ndarray):
        data = self.payload
        data['base64Image'] = 'data:image/jpg;base64,' + \
            base64.b64encode(cv2.imencode('.jpg', image)[1].tobytes()).decode()

        retry_times = 1
        while True:
            try:
                r = requests.post(
                    self.endpoint,
                    data=data,
                    timeout=self.timeout,
                )
                break
            except Exception as e:
                logger.warning(e)
                logger.debug(traceback.format_exc())
                retry_times -= 1
                if retry_times > 0:
                    logger.warning('重试中……')
                else:
                    logger.warning('无网络或网络故障，无法连接到 OCR Space')
                    return []
        try:
            return self._parse(r.json())
        except Exception as e:
            logger.debug(e)
            return []

    def predict(self, image, scope):
        ret = self.ocr_image(
            image[scope[0][1]:scope[2][1], scope[0][0]:scope[2][0]])
        if len(ret) == 0:
            return None
        return fix(ret[0])
