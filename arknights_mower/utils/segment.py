import cv2
import traceback
import imagehash
import numpy as np
from matplotlib import pyplot as plt
from PIL import Image, ImageDraw, ImageFont

from .log import logger
from .recognize import RecognizeError
from ..data.agent import agent_list
from ..data.ocr import ocr_error
from ..ocr import ocrhandle
from .image import rgb2gray, margin
from ..__init__ import __rootdir__


class FloodCheckFailed(Exception):
    pass


agent_ahash = None


def agent_ahash_init():
    global agent_ahash
    if agent_ahash is None:
        logger.debug('agent_ahash_init')
        agent_ahash = {}
        font = ImageFont.truetype(
            f'{__rootdir__}/fonts/SourceHanSansSC-Bold.otf', size=30, encoding='utf-8')
        for text in agent_list:
            dt = np.zeros((500, 500, 3), dtype=int)
            img = Image.fromarray(np.uint8(dt))
            ImageDraw.Draw(img).text((0, 0), text, (255, 255, 255), font=font)
            img = np.array(img)

            x0 = 0
            while (img[:, x0] == 0).all():
                x0 += 1
            x1 = img.shape[1]
            while (img[:, x1-1] == 0).all():
                x1 -= 1
            y0 = 0
            while (img[y0, x0:x1] == 0).all():
                y0 += 1
            y1 = img.shape[0]
            while (img[y1-1, x0:x1] == 0).all():
                y1 -= 1

            agent_ahash[text] = str(imagehash.average_hash(
                Image.fromarray(img[y0:y1, x0:x1]), 16))


def get_poly(x1, x2, y1, y2):
    x1, x2 = int(x1), int(x2)
    y1, y2 = int(y1), int(y2)
    return np.array([[x1, y1], [x1, y2], [x2, y2], [x2, y1]])


def credit(im, draw=False):
    """
    信用交易所特供的图像分割算法
    """
    try:
        x, y, z = im.shape

        l, r = 0, y
        while np.max(im[:, r-1]) < 100:
            r -= 1
        while np.max(im[:, l]) < 100:
            l += 1

        def average(i):
            n, s = 0, 0
            for j in range(l, r):
                if im[i, j, 0] == im[i, j, 1] and im[i, j, 0] == im[i, j, 2]:
                    n += 1
                    s += im[i, j, 0]
            return int(s / n)

        def ptp(j):
            mx = -999999
            mn = 999999
            for i in range(up, up2):
                mn = min(mn, im[i, j, 0])
                mx = max(mx, im[i, j, 0])
            return mx - mn

        up = 0
        fg = False
        while fg == False or average(up) >= 250:
            fg |= average(up) >= 250
            up += 1

        up2 = up
        fg = False
        while fg == False or average(up2) < 220:
            fg |= average(up2) < 220
            up2 += 1

        down = x - 1
        while average(down) < 180:
            down -= 1

        right = y - 1
        while ptp(right) < 50:
            right -= 1

        left = 0
        while ptp(left) < 50:
            left += 1

        split_x = [left] + [left + (right - left) //
                            5 * i for i in range(1, 5)] + [right]
        split_y = [up, (up + down) // 2, down]

        ret = []
        for x1, x2 in zip(split_x[:-1], split_x[1:]):
            for y1, y2 in zip(split_y[:-1], split_y[1:]):
                ret.append(((x1, y1), (x2, y2)))

        if draw:
            for x1, x2 in zip(split_x[:-1], split_x[1:]):
                for y1, y2 in zip(split_y[:-1], split_y[1:]):
                    cv2.polylines(im, [get_poly(x1, x2, y1, y2)],
                                  True, 0, 10, cv2.LINE_AA)
            plt.imshow(im)
            plt.show()

        logger.debug(f'segment.credit: {ret}')
        return ret

    except Exception as e:
        logger.debug(traceback.format_exc())
        raise RecognizeError


def recruit(im, draw=False):
    """
    公招特供的图像分割算法
    """
    try:
        x, y, z = im.shape
        u, d = 0, x
        l, r = y//2-100, y//2-50

        def adj_x(i):
            if i == 0:
                return 0
            s = 0
            for j in range(l, r):
                for k in range(3):
                    s += abs(int(im[i, j, k]) - int(im[i-1, j, k]))
            return int(s / (r-l))

        def adj_y(j):
            if j == 0:
                return 0
            s = 0
            for i in range(u, d):
                for k in range(3):
                    s += abs(int(im[i, j, k]) - int(im[i, j-1, k]))
            return int(s / (d-u))

        def average(i):
            s = 0
            for j in range(l, r):
                s += np.sum(im[i, j, :3])
            return int(s / (r-l) / 3)

        def minus(i):
            s = 0
            for j in range(l, r):
                s += int(im[i, j, 2]) - int(im[i, j, 0])
            return int(s / (r-l))

        up = 0
        while minus(up) > -100:
            up += 1
        while not (adj_x(up) > 80 and minus(up) > -10 and average(up) > 210):
            up += 1
        u, d = up-90, up-40

        down = x - 2
        while adj_x(down+1) < 100:
            down -= 1

        left = 0
        while np.max(im[:, left]) < 100:
            left += 1
        left += 1
        while adj_y(left) < 50:
            left += 1

        right = y - 1
        while np.max(im[:, right]) < 100:
            right -= 1
        while adj_y(right) < 50:
            right -= 1

        split_x = [left, (left + right) // 2, right]
        split_y = [up, (up + down) // 2, down]

        ret = []
        for x1, x2 in zip(split_x[:-1], split_x[1:]):
            for y1, y2 in zip(split_y[:-1], split_y[1:]):
                ret.append(((x1, y1), (x2, y2)))

        if draw:
            for x1, x2 in zip(split_x[:-1], split_x[1:]):
                for y1, y2 in zip(split_y[:-1], split_y[1:]):
                    cv2.polylines(im, [get_poly(x1, x2, y1, y2)],
                                  True, 0, 10, cv2.LINE_AA)
            plt.imshow(im)
            plt.show()

        logger.debug(f'segment.recruit: {ret}')
        return ret

    except Exception as e:
        logger.debug(traceback.format_exc())
        raise RecognizeError


def base(im, central, draw=False):
    """
    基建布局的图像分割算法
    """
    try:
        ret = {}

        x1, y1 = central[0]
        x2, y2 = central[1]
        alpha = (y2 - y1) / 160
        x1 -= 170 * alpha
        x2 += 182 * alpha
        y1 -= 67 * alpha
        y2 += 67 * alpha
        central = get_poly(x1, x2, y1, y2)
        ret['central'] = central

        for i in range(1, 5):
            y1 = y2 + 25 * alpha
            y2 = y1 + 134 * alpha
            if i & 1:
                dormitory = get_poly(x1, x2 - 158 * alpha, y1, y2)
            else:
                dormitory = get_poly(x1 + 158 * alpha, x2, y1, y2)
            ret[f'dormitory_{i}'] = dormitory

        x1, y1 = ret['dormitory_1'][0]
        x2, y2 = ret['dormitory_1'][2]

        x1 = x2 + 419 * alpha
        x2 = x1 + 297 * alpha
        factory = get_poly(x1, x2, y1, y2)
        ret[f'factory'] = factory

        y2 = y1 - 25 * alpha
        y1 = y2 - 134 * alpha
        meeting = get_poly(x1 - 158 * alpha, x2, y1, y2)
        ret[f'meeting'] = meeting

        y1 = y2 + 25 * alpha
        y2 = y1 + 134 * alpha
        y1 = y2 + 25 * alpha
        y2 = y1 + 134 * alpha
        contact = get_poly(x1, x2, y1, y2)
        ret[f'contact'] = contact

        y1 = y2 + 25 * alpha
        y2 = y1 + 134 * alpha
        train = get_poly(x1, x2, y1, y2)
        ret[f'train'] = train

        for floor in range(1, 4):
            x1, y1 = ret[f'dormitory_{floor}'][0]
            x2, y2 = ret[f'dormitory_{floor}'][2]
            x2 = x1 - 102 * alpha
            x1 = x2 - 295 * alpha
            if floor & 1 == 0:
                x2 = x1 - 24 * alpha
                x1 = x2 - 295 * alpha
            room = get_poly(x1, x2, y1, y2)
            ret[f'room_{floor}_3'] = room
            x2 = x1 - 24 * alpha
            x1 = x2 - 295 * alpha
            room = get_poly(x1, x2, y1, y2)
            ret[f'room_{floor}_2'] = room
            x2 = x1 - 24 * alpha
            x1 = x2 - 295 * alpha
            room = get_poly(x1, x2, y1, y2)
            ret[f'room_{floor}_1'] = room

        if draw:
            polys = list(ret.values())
            cv2.polylines(im, polys, True, (255, 0, 0), 10, cv2.LINE_AA)
            plt.imshow(im)
            plt.show()

        logger.debug(f'segment.base: {ret}')
        return ret

    except Exception as e:
        logger.debug(traceback.format_exc())
        raise RecognizeError


def worker(im, draw=False):
    """
    进驻总览的图像分割算法
    """
    try:
        h, w, _ = im.shape

        l, r = 0, w
        while np.max(im[:, r-1]) < 100:
            r -= 1
        while np.max(im[:, l]) < 100:
            l += 1

        x0 = r-1
        while np.average(im[:, x0, 1]) >= 100:
            x0 -= 1
        x0 -= 2

        seg = []
        remove_mode = False
        pre, st = int(im[0, x0, 1]), 0
        for y in range(1, h):
            remove_mode |= im[y, x0, 0] - im[y, x0, 1] > 40
            if np.ptp(im[y, x0]) <= 1 or int(im[y, x0, 0]) - int(im[y, x0, 1]) > 40:
                now = int(im[y, x0, 1])
                if abs(now - pre) > 20:
                    if now < pre and st == 0:
                        st = y
                    elif now > pre and st != 0:
                        seg.append((st, y))
                        st = 0
                pre = now
            elif st != 0:
                seg.append((st, y))
                st = 0
        # if st != 0:
        #     seg.append((st, h))
        logger.debug(seg)

        remove_button = get_poly(x0-10, x0, seg[0][0], seg[0][1])
        seg = seg[1:]

        for i in range(1, len(seg)):
            if seg[i][1] - seg[i][0] > 9:
                x1 = x0
                while im[seg[i][1]-3, x1-1, 2] < 100:
                    x1 -= 1
                break

        ret = []
        for i in range(len(seg)):
            if seg[i][1] - seg[i][0] > 9:
                ret.append(get_poly(x1, x0, seg[i][0], seg[i][1]))

        if draw:
            cv2.polylines(im, ret, True, (255, 0, 0), 10, cv2.LINE_AA)
            plt.imshow(im)
            plt.show()

        logger.debug(f'segment.worker: {[x.tolist() for x in ret]}')
        return ret, remove_button, remove_mode

    except Exception as e:
        logger.debug(traceback.format_exc())
        raise RecognizeError


def agent(im, draw=False):
    """
    干员总览的图像分割算法
    """
    try:
        h, w, _ = im.shape

        # gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
        # gray = 255 - gray

        l, r = 0, w
        while np.max(im[:, r-1]) < 100:
            r -= 1
        while np.max(im[:, l]) < 100:
            l += 1

        x0 = l + 1
        while not (im[h-1, x0-1, 0] > im[h-1, x0, 0] + 10 and abs(int(im[h-1, x0, 0]) - int(im[h-1, x0+1, 0])) < 5):
            x0 += 1

        ocr = ocrhandle.predict(im[:, x0:r])

        segs = [(min(x[2][0][1], x[2][1][1]), max(x[2][2][1], x[2][3][1]))
                for x in ocr if x[1] in agent_list]
        while True:
            _a, _b = None, None
            for i in range(len(segs)):
                for j in range(len(segs)):
                    if i != j and (segs[i][0] <= segs[j][0] <= segs[i][1] or segs[i][0] <= segs[j][1] <= segs[i][1]):
                        _a, _b = segs[i], segs[j]
                        break
                if _b is not None:
                    break
            if _b is not None:
                segs.remove(_a)
                segs.remove(_b)
                segs.append((min(_a[0], _b[0]), max(_a[1], _b[1])))
            else:
                break
        segs = sorted(segs)
        for x in segs:
            if x[1] < h // 2:
                y0, y1 = x
            y2, y3 = x
        card_gap = y1 - y0
        logger.debug([y0, y1, y2, y3])

        x_set = set()
        for x in ocr:
            if x[1] in agent_list and (y0 <= x[2][0][1] <= y1 or y2 <= x[2][0][1] <= y3):
                x_set.add(x[2][1][0])
                x_set.add(x[2][2][0])
        x_set = sorted(x_set)
        logger.debug(x_set)
        x_set = [x_set[0]] + \
            [y for x, y in zip(x_set[:-1], x_set[1:]) if y - x > 80]
        gap = [y - x for x, y in zip(x_set[:-1], x_set[1:])]
        gap = [x for x in gap if x - np.min(gap) < 40]
        gap = int(np.average(gap))
        for x, y in zip(x_set[:-1], x_set[1:]):
            if y - x > 40:
                gap_num = round((y - x) / gap)
                for i in range(1, gap_num):
                    x_set.append(int(x + (y - x) / gap_num * i))
        while np.min(x_set) > 0:
            x_set.append(np.min(x_set) - gap)
        while np.max(x_set) < r - x0:
            x_set.append(np.max(x_set) + gap)
        x_set = sorted(x_set)
        logger.debug(x_set)

        ret = []
        for x1, x2 in zip(x_set[:-1], x_set[1:]):
            if 0 <= x1+card_gap and x0+x2+5 <= r:
                ret += [get_poly(x0+x1+card_gap, x0+x2+5, y0, y1),
                        get_poly(x0+x1+card_gap, x0+x2+5, y2, y3)]

        def poly_center(poly):
            return (np.average([x[0] for x in poly]), np.average([x[1] for x in poly]))

        def in_poly(poly, p):
            return poly[0, 0] <= p[0] <= poly[2, 0] and poly[0, 1] <= p[1] <= poly[2, 1]

        # if draw:
        #     cv2.polylines(im, ret, True, (255, 0, 0), 3, cv2.LINE_AA)
        #     plt.imshow(im)
        #     plt.show()

        def flood(img, dt):
            h, w = img.shape
            while True:
                pre_count = (dt > 0).sum()
                for x in range(1, w):
                    dt[:, x][(dt[:, x-1] > 0) & (img[:, x] > 0)] = 1
                for y in range(h-2, -1, -1):
                    dt[y][(dt[y+1] > 0) & (img[y] > 0)] = 1
                for x in range(w-2, -1, -1):
                    dt[:, x][(dt[:, x+1] > 0) & (img[:, x] > 0)] = 1
                for y in range(1, h):
                    dt[y][(dt[y-1] > 0) & (img[y] > 0)] = 1
                if pre_count == (dt > 0).sum():
                    break


        def ahash_recog(origin_img, scope):
            agent_ahash_init()
            origin_img = origin_img[scope[0, 1]:scope[2, 1], scope[0, 0]:scope[2, 0]]
            h, w = origin_img.shape[:2]
            thresh = 70
            while True:
                try:
                    img = rgb2gray(margin(origin_img, thresh))
                    dt = np.zeros((h, w), dtype=np.uint8)
                    for y in range(h):
                        if img[y, w-1] != 0:
                            dt[y, w-1] = 1
                    flood(img, dt)
                    for y in range(h-1, h//2, -1):
                        count = 0
                        for x in range(w-1, -1, -1):
                            if dt[y, x] != 0:
                                count += 1
                            else:
                                break
                        if not (dt[y, :] > 0).all():
                            for x in range(w):
                                if dt[y, x] != 0:
                                    count += 1
                                else:
                                    break
                        if (dt[y] > 0).sum() != count:
                            logger.debug(f'{y}, {count}')
                            raise FloodCheckFailed
                    
                    for y in range(h):
                        if img[y, 0] != 0:
                            dt[y, 0] = 1
                    for x in range(w):
                        if img[h-1, x] != 0:
                            dt[h-1, x] = 1
                        if img[0, x] != 0:
                            dt[0, x] = 1
                    flood(img, dt)
                    img[dt > 0] = 0
                    if (img > 0).sum() == 0:
                        raise FloodCheckFailed
                    
                    x0, x1, y0, y1 = 0, w, 0, h
                    while True:
                        while (img[y0:y1, x0] == 0).all():
                            x0 += 1
                        while (img[y0:y1, x1-1] == 0).all():
                            x1 -= 1
                        while (img[y0, x0:x1] == 0).all():
                            y0 += 1
                        while (img[y1-1, x0:x1] == 0).all():
                            y1 -= 1
                        for x in range(x0, x1-10+1):
                            if (img[y0:y1, x:x+10] == 0).all():
                                x0 = x
                                break
                        if (img[y0:y1, x0] == 0).all():
                            continue
                        for y in range(y0, y1-10+1):
                            if (img[y:y+10, x0:x1] == 0).all():
                                y0 = y
                                break
                        if (img[y0, x0:x1] == 0).all():
                            continue
                        break

                    dt = np.zeros((y1-y0, x1-x0, 3), dtype=np.uint8)
                    dt[:, :, 0] = img[y0:y1, x0:x1]
                    dt[:, :, 1] = img[y0:y1, x0:x1]
                    dt[:, :, 2] = img[y0:y1, x0:x1]
                    ahash = str(imagehash.average_hash(Image.fromarray(dt), 16))
                    p = [(bin(int(ahash, 16) ^ int(agent_ahash[x], 16)).count('1'), x) for x in agent_ahash.keys()]
                    p = sorted(p)
                    logger.debug(p[:10])
                    if p[1][0] - p[0][0] < 10:
                        raise FloodCheckFailed
                    logger.debug(p[0][1])
                    return p[0][1]
                    
                except FloodCheckFailed:
                    thresh += 5
                    logger.debug(f'add thresh to {thresh}')
                    if thresh > 100:
                        break
                    continue
            return None

        ret_succ = []
        ret_fail = []
        ret_agent = []
        for poly in ret:
            found_ocr, fx = None, 0
            for x in ocr:
                cx, cy = poly_center(x[2])
                if in_poly(poly, (cx+x0, cy)) and cx > fx:
                    fx = cx
                    found_ocr = x

            if found_ocr is not None:
                x = found_ocr
                if x[1] in agent_list:
                    ret_agent.append(x[1])
                    ret_succ.append(poly)
                    continue
                res = ocrhandle.predict(
                    margin(im[poly[0, 1]-20:poly[2, 1]+20, poly[0, 0]-20:poly[2, 0]+20], 70))
                if len(res) > 0 and res[0][1] in agent_list:
                    x = res[0]
                    ret_agent.append(x[1])
                    ret_succ.append(poly)
                    continue
                res = ahash_recog(im, poly)
                if res is not None:
                    logger.warning(f'干员名称识别异常：{x[1]} 应为 {res}')
                    ocr_error[x[1]] = res
                    ret_agent.append(res)
                    ret_succ.append(poly)
                    continue
                logger.warning(
                    f'干员名称识别异常：{x[1]} 为不存在的数据，请报告至 https://github.com/Konano/arknights-mower/issues')
            else:
                res = ocrhandle.predict(
                    margin(im[poly[0, 1]-20:poly[2, 1]+20, poly[0, 0]-20:poly[2, 0]+20], 70))
                if len(res) > 0 and res[0][1] in agent_list:
                    res = res[0][1]
                    ret_agent.append(res)
                    ret_succ.append(poly)
                    continue
                res = ahash_recog(im, poly)
                if res is not None:
                    ret_agent.append(res)
                    ret_succ.append(poly)
                    continue
                logger.warning(f'干员名称识别异常：区域 {poly}')
            ret_fail.append(poly)

        if draw and len(ret_fail):
            cv2.polylines(im, ret_fail, True, (255, 0, 0), 3, cv2.LINE_AA)
            plt.imshow(im)
            plt.show()

        logger.debug(f'segment.agent: {ret_agent}')
        logger.debug(f'segment.agent: {[x.tolist() for x in ret]}')
        return list(zip(ret_agent, ret_succ))

    except Exception as e:
        logger.debug(traceback.format_exc())
        raise RecognizeError(e)
