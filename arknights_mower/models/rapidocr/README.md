# RapidOCR 模型

Mower 使用 RapidOCR 3.10.0 和以下 PP-OCRv6 tiny ONNX 模型。文件直接取自 RapidAI 的版本化模型仓库，未修改模型权重或元数据；识别字典包含在识别模型的 ONNX 元数据中。

| 文件 | 字节数 | SHA-256 | 下载来源 |
| --- | --- | --- | --- |
| `PP-OCRv6_det_tiny.onnx` | 1829618 | `f42c0fbd294d95eac1a550e131b277dac97462c8025fa4b6c3cec1b7894bd3d5` | [RapidAI v3.10.0](https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.10.0/onnx/PP-OCRv6/det/PP-OCRv6_det_tiny.onnx) |
| `PP-OCRv6_rec_tiny.onnx` | 4489813 | `e16e242de5937ad92609223f19bc2aff3727ee40b095f996907c24749bad251b` | [RapidAI v3.10.0](https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.10.0/onnx/PP-OCRv6/rec/PP-OCRv6_rec_tiny.onnx) |

文件摘要与 [RapidOCR 3.10.0 模型登记表](https://github.com/RapidAI/RapidOCR/blob/v3.10.0/python/rapidocr/default_models.yaml)一致。上游模型权重版权属于 Baidu 和适用的 PaddleOCR 权利人，RapidOCR 提供 ONNX 转换及打包。PaddlePaddle 的官方 [tiny 检测模型卡](https://huggingface.co/PaddlePaddle/PP-OCRv6_tiny_det_onnx)与 [tiny 识别模型卡](https://huggingface.co/PaddlePaddle/PP-OCRv6_tiny_rec_onnx)均声明 Apache-2.0；本目录保留 RapidOCR 3.10.0 随附的 [Apache-2.0 许可证](LICENSE)，其中同时保留 RapidOCR Authors 的版权声明。

方向分类继续使用 RapidOCR 包内的 `models/ch_ppocr_mobile_v2.0_cls_mobile.onnx`，SHA-256 为 `e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c`。其上游来源及声明保留在 [RapidOCR 原始模型许可说明](UPSTREAM_MODEL_LICENSES.md)中；该原始说明只涵盖其表内模型，tiny 的许可依据为上述官方模型卡。桌面包仅收集 SDK 配置、此分类模型和 Mower 自带的两个 tiny 模型，不收集 SDK 默认的 small 检测、识别模型。
