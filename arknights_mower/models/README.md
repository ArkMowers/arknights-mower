# Models

## dbnet.onnx

DBNET 的模型文件，负责提取图像中的文字

## crnn_lite_lstm.onnx

CRNN 的轻量型模型文件，负责识别图像中的文字

## svm.model

SVM 分类器的模型文件，负责图像匹配判定

## depot.pkl

仓库物品的knn模型，负责仓库中的物品

## stage_code.npz

关卡详情页的大号关号使用 AEwide。运行时按笔画和宽高比匹配每个字符；模型包含大写字母、数字及连字符的三组字号。用 MowerFonts 的原字体运行 `python build_stage_code_model.py /path/to/AEwide.otf` 可重新生成。普通与突袭详情的关号节点均为 `panel_stage_title/label_stage_code`。
