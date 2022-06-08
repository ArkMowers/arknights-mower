import numpy as np
import onnxruntime as rt
from PIL import Image

from .keys import alphabetChinese as alphabet
from .utils import resizeNormalize, strLabelConverter

converter = strLabelConverter(''.join(alphabet))


class CRNNHandle:
    def __init__(self, model_path):
        sess_options = rt.SessionOptions()
        sess_options.log_severity_level = 3
        self.sess = rt.InferenceSession(model_path, sess_options)

    def predict(self, image):
        scale = image.size[1] * 1.0 / 32
        w = image.size[0] / scale
        w = int(w)
        transformer = resizeNormalize((w, 32))
        image = transformer(image)
        image = image.transpose(2, 0, 1)
        transformed_image = np.expand_dims(image, axis=0)
        transformed_image = np.array([[transformed_image[0, 0]] * 3])
        preds = self.sess.run(
            ['out'], {'input': transformed_image.astype(np.float32)})
        preds = preds[0]
        length = preds.shape[0]
        preds = preds.reshape(length, -1)
        preds = np.argmax(preds, axis=1)
        preds = preds.reshape(-1)
        sim_pred = converter.decode(preds, length, raw=False)
        return sim_pred

    def predict_rbg(self, image):
        scale = image.size[1] * 1.0 / 32
        w = image.size[0] / scale
        w = int(w)
        image = image.resize((w, 32), Image.BILINEAR)
        image = np.array(image, dtype=np.float32)
        image -= 127.5
        image /= 127.5
        image = image.transpose(2, 0, 1)
        transformed_image = np.expand_dims(image, axis=0)
        preds = self.sess.run(
            ['out'], {'input': transformed_image.astype(np.float32)})
        preds = preds[0]
        length = preds.shape[0]
        preds = preds.reshape(length, -1)
        preds = np.argmax(preds, axis=1)
        preds = preds.reshape(-1)
        sim_pred = converter.decode(preds, length, raw=False)
        return sim_pred
