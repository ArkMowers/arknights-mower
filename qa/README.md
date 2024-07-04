---
sort: 4
---
# 常见问题 Q&A

## 运行时出现错误：’NoneType object has no attribute shape‘

此为缓存路径出现中文字符导致，多半是因为window用户名设置为中文了，请修改用户名为英文

## 大量出现「识别出了点小差错」并卡死在特定界面

当前版本在非 1080p（1920x1080）分辨率下，对于部分界面的识别可能会出现错误，将模拟器修改为 1080p 分辨率可以解决大部分问题。如果在分辨率修改后问题仍未解决，可以在 Issue 页面提出。

## 提示「未检测到相应设备。请运行 `adb devices` 确认列表中列出了目标模拟器或设备。」

- 夜神（Nox）模拟器：[解决办法](https://github.com/Konano/arknights-mower/issues/117#issuecomment-1118447644)

## ![image](https://github.com/ArkMowers/arknights-mower/assets/33809511/fe6eafd6-280b-444c-b4e3-630496a0d5a4) 
 最后提示Unable to open database file 
 请把旧版文件夹下的 tmp 文件夹复制到新版文件夹中；否则，请在mower的文件夹里手动建立tmp文件夹，并把群文件工具文件夹中的data.db放到tmp文件夹中。不便之处，敬请谅解。




