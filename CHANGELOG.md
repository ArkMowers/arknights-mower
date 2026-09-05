# CHANGELOG

## 4.1.6-alpha.2 - 2026-09-03

### New

- 新增资源更新与热更通道 [(#923)](https://github.com/ArkMowers/arknights-mower/pull/923) @NiceAfternoon
- 配置文件改走原子写并挪到 config/ 目录 [(#920)](https://github.com/ArkMowers/arknights-mower/pull/920) @NiceAfternoon

### Bug Fixes

- 修复排班图片导入在导出图被改过后失败 [(#922)](https://github.com/ArkMowers/arknights-mower/pull/922) @NiceAfternoon
- 修复一键替换干员漏换主副表全部字段的问题 [(#921)](https://github.com/ArkMowers/arknights-mower/pull/921) @NiceAfternoon
- 修复窗口尺寸配置不生效 [(#919)](https://github.com/ArkMowers/arknights-mower/pull/919) @NiceAfternoon
- 修复连接错误被误判导致运行中的游戏退出与资源残留 [(#918)](https://github.com/ArkMowers/arknights-mower/pull/918) @NiceAfternoon
- 修复 Linux 独立包缺少 pywebview 的 GTK 后端导致窗口无法启动 [(#917)](https://github.com/ArkMowers/arknights-mower/pull/917) @NiceAfternoon

### Improvements

- 精简识别热路径 DEBUG 日志 [(#925)](https://github.com/ArkMowers/arknights-mower/pull/925) @NiceAfternoon
- 图像识别改用纯 numpy 实现缩减打包体积 [(#916)](https://github.com/ArkMowers/arknights-mower/pull/916) @NiceAfternoon

### Dependencies

- changelog 按版本类型选取基准并新增依赖升级分组 [(#913)](https://github.com/ArkMowers/arknights-mower/pull/913) @NiceAfternoon
- 升级 echarts、vite、vitest 等前端依赖 [(#912)](https://github.com/ArkMowers/arknights-mower/pull/912) @NiceAfternoon

**Full Changelog**: [v4.1.6-alpha.1...v4.1.6-alpha.2](https://github.com/ArkMowers/arknights-mower/compare/v4.1.6-alpha.1...v4.1.6-alpha.2)

## 4.1.6-alpha.1 - 2026-09-01

### New

- 支持正式版与 alpha 的跨平台构建发布 ([#911](https://github.com/ArkMowers/arknights-mower/pull/911) @NiceAfternoon)
- 创建专精计划后立即开始训练 (@NiceAfternoon)
- 新增按干员是否空闲筛选专精计划 (@NiceAfternoon)
- 新增专精推荐显示真实技能名和显式保存专精计划与路线配置 (@NiceAfternoon)
- 新增协助位设置中的配置，优化专精计划管理，并将手动专精任务改为专精计划创建 (@NiceAfternoon)
- 新增全自动专精全局开关，专精相关任务由仓库扫描触发 (@NiceAfternoon)
- 专精训练进度改为按训练室画面识别结果更新 (@NiceAfternoon)
- 专精数据新增干员技能名称供界面显示与识别核对 (@NiceAfternoon)
- 修改专精计划状态与路线设置为数据库保存 (@NiceAfternoon)
- 新增数据库管理，并支持按类别删除记录 (@NiceAfternoon)
- 新增领取会客室信息板信用 ([#885](https://github.com/ArkMowers/arknights-mower/pull/885) @NiceAfternoon)
- 新增启动游戏自定义命令选项 ([#883](https://github.com/ArkMowers/arknights-mower/pull/883) @ALEXsun0)
- 新增缓存清零后刷新副表开关并修复训练室读取条件 ([#881](https://github.com/ArkMowers/arknights-mower/pull/881) @ALEXsun0)
- 优化全自动专精状态机，整合训练室状态检测到心情读取 ([#880](https://github.com/ArkMowers/arknights-mower/pull/880) @NiceAfternoon)
- 初步实现调用 MAA 刷生息演算 ([#878](https://github.com/ArkMowers/arknights-mower/pull/878) @NiceAfternoon)
- add MAA mac compatibility check ([#877](https://github.com/ArkMowers/arknights-mower/pull/877) @ALEXsun0)
- 重构全自动专精调度、增加加工站干员配置并修复邮件和无法删除的加工配置问题 ([#873](https://github.com/ArkMowers/arknights-mower/pull/873) @NiceAfternoon)
- 完善全自动专精功能 ([#871](https://github.com/ArkMowers/arknights-mower/pull/871) @NiceAfternoon)
- 实现全自动专精功能并优化合成方案配置 ([#862](https://github.com/ArkMowers/arknights-mower/pull/862) @mikuzc)
- add Closure order in report and trade order analysis ([#865](https://github.com/ArkMowers/arknights-mower/pull/865) @NiceAfternoon)
- 周计划关卡按开放时间过滤，活动期间可关闭 ([#860](https://github.com/ArkMowers/arknights-mower/pull/860) @clousky2020)
- 可露希尔 跑单 (@Shawnsdaddy)
- APIKEY 后门 (@Shawnsdaddy)
- 验证码solver (@Shawnsdaddy)
- changelog pop up (@Shawnsdaddy)
- 为 Mower AI 助手输出内容添加 markdown 渲染 ([#842](https://github.com/ArkMowers/arknights-mower/pull/842) @NiceAfternoon)
- add one more cause (@Shawnsdaddy)
- 周计划方案 (@Shawnsdaddy)
- 漏单分析 agent (@Shawnsdaddy)
- 完善森空岛签到功能并优化前端显示逻辑 ([#838](https://github.com/ArkMowers/arknights-mower/pull/838) @NiceAfternoon)
- 增加了森空岛的终末地签到和测试签到功能 ([#827](https://github.com/ArkMowers/arknights-mower/pull/827) @NiceAfternoon)
- MuMu截图增强 (@Shawnsdaddy)
- 添加多开器一键启动全部实例 (@yufuyufuyu)
- 分类新增 (@Shawnsdaddy)
- #743 新增检测 (@Shawnsdaddy)

### Bug Fixes

- 修复计划外训练与换人后任务、通知的干员、技能与档位显示 (@NiceAfternoon)
- 修复清空超时任务后只剩远期专精任务时基建安排不处理 (@NiceAfternoon)
- 修复替换组干员名称含引号时心情曲线查询失败 (@NiceAfternoon)
- 修复专精计划页显示无效的三星筛选项 (@NiceAfternoon)
- 修复任务接口未校验 Webview Token (@NiceAfternoon)
- 修复错误的创建专精任务，应该使用MasterySync正确地创建任务 ([#906](https://github.com/ArkMowers/arknights-mower/pull/906) @GodofTheFallen)
- 修复 Maa 连通性检测误报 ([#901](https://github.com/ArkMowers/arknights-mower/pull/901) @ALEXsun0)
- 最小化修复mower无法停止问题 ([#892](https://github.com/ArkMowers/arknights-mower/pull/892) @ALEXsun0)
- 修复启动前 MAA 连通性检查时序 ([#889](https://github.com/ArkMowers/arknights-mower/pull/889) @ALEXsun0)
- 统一任务间休眠收口，修复休息期间 /status 的 sleeping 状态 ([#884](https://github.com/ArkMowers/arknights-mower/pull/884) @djkcyl)
- 修复训练室空闲检测误判，优化全自动专精稳定性 ([#875](https://github.com/ArkMowers/arknights-mower/pull/875) @NiceAfternoon)
- 添加缺失的截图 (@Konano)
- 修复识别跑单订单价值时模板误匹配 ([#858](https://github.com/ArkMowers/arknights-mower/pull/858) @NiceAfternoon)
- 4.1.6专精模块修复完善 ([#855](https://github.com/ArkMowers/arknights-mower/pull/855) @mikuzc)
- release warpup (@Shawnsdaddy)
- 修复房间干员识别、用尽任务时间和见习任务跳过 ([#848](https://github.com/ArkMowers/arknights-mower/pull/848) @ALEXsun0)
- 修复跑单订单类型误判并适配新增材料分类 ([#851](https://github.com/ArkMowers/arknights-mower/pull/851) @NiceAfternoon)
- 修复 auto_get_res_new.py 中的解析逻辑，适配部分游戏数据字段从数字改为字符串 ([#849](https://github.com/ArkMowers/arknights-mower/pull/849) @NiceAfternoon)
- 处理闪断更新公告中的 24:00 时间 ([#850](https://github.com/ArkMowers/arknights-mower/pull/850) @clousky2020)
- ruff check (@Shawnsdaddy)
- 修复了连战次数识别错误和理智获取错误的问题并为更新日志添加 markdown 渲染 ([#843](https://github.com/ArkMowers/arknights-mower/pull/843) @NiceAfternoon)
- add missing code (@Shawnsdaddy)
- unit test failures (@Shawnsdaddy)
- ruff format (@Shawnsdaddy)
- 修复公招 (@Shawnsdaddy)
- 支持旧版本mumuapi (@yufuyufuyu)
- 滑动修复 (@Shawnsdaddy)
- 修复 option 不显示 (@Shawnsdaddy)
- 修复家具零件碳素组不合成 ([#778](https://github.com/ArkMowers/arknights-mower/pull/778) @HoverSoul)
- 解决linux中找不到zbar共享库问题 ([#780](https://github.com/ArkMowers/arknights-mower/pull/780) @pikahan)
- 修复：公招截图太快导致tag重复识别 ([#775](https://github.com/ArkMowers/arknights-mower/pull/775) @HoverSoul)
- 修复op_data.party_time未初始化问题 & 家具零件垫刀问题 ([#772](https://github.com/ArkMowers/arknights-mower/pull/772) @HoverSoul @Shawnsdaddy)
- 修复训练free /current bug (@Shawnsdaddy)
- 九色鹿逻辑判定修复 (@Shawnsdaddy)
- 仅在party时间过期或不存在时更新op_data.party_time，以修复跃跃排班表失效 (@HoverSoul)
- 计算点击次数方法修复 (@Shawnsdaddy)
- 修复边际case (@Shawnsdaddy)
- 无缝加工站bug修复+添加graph (@Shawnsdaddy)

### Improvements

- 提取基建进驻排序坐标、无人机界面等待与跑单时间读取为共用函数 (@NiceAfternoon)
- 优化前后端体积与启动性能，修复基建报表数据读取 ([#904](https://github.com/ArkMowers/arknights-mower/pull/904) @NiceAfternoon)
- 4.1.6仓库刷新逻辑优化 ([#857](https://github.com/ArkMowers/arknights-mower/pull/857) @mikuzc)
- 版本号更新 (@Shawnsdaddy)
- 游戏资源更新 (@Shawnsdaddy)
- 资源更新 (@Shawnsdaddy)
- 识别图片更新 (@Shawnsdaddy)
- 版本更新 (@Shawnsdaddy)
- 游戏数据更新 (@Shawnsdaddy)
- UI优化 (@Shawnsdaddy)
- 九色鹿优化 (@Shawnsdaddy)
- tool 更新 (@Shawnsdaddy)
- 游戏资源更新 (@Shawnsdaddy)
- 资源更新 (@Shawnsdaddy)
- 游戏资源更新 (@Shawnsdaddy)
- 提示词优化 (@Shawnsdaddy)
- 导航更新 (@Shawnsdaddy)
- 用尽任务优化 (@Anyk00)
- MAAapi更新 (@Anyk00)
- 九色鹿任务条件判定更新 (@Shawnsdaddy)
- 适配更新 (@Shawnsdaddy)
- 优化开发的打包步骤和文档 (@servis)
- 更新Q群 (@Shawnsdaddy)

### Maintenance

- run dev_tools formatting (@Shawnsdaddy)

### Documentation

- 为 README 添加 Docker 部署文档链接 ([#866](https://github.com/ArkMowers/arknights-mower/pull/866) @dhujsi)
- 更新 README 文档，修正格式和内容 (@Konano)
- 本地文档复活 (@Shawnsdaddy)

### Other

- 修复公招测试因模拟 NumPy 导致模型数据导入失败 (@NiceAfternoon)
- 更新 CHANGELOG 至 4.1.5.8 并优化打包体积 ([#903](https://github.com/ArkMowers/arknights-mower/pull/903) @NiceAfternoon)
- 更新游戏数据，修复专精调度/导航/日志等问题 ([#902](https://github.com/ArkMowers/arknights-mower/pull/902) @Shawnsdaddy @NiceAfternoon)
- Update master plan ([#895](https://github.com/ArkMowers/arknights-mower/pull/895) @Shawnsdaddy)
- 更新游戏数据（新增干员机械师） ([#899](https://github.com/ArkMowers/arknights-mower/pull/899) @WufeiHalf)
- 更新 CHANGELOG 至 4.1.5.7 并更新游戏数据 ([#890](https://github.com/ArkMowers/arknights-mower/pull/890) @NiceAfternoon)
- Update master plan ([#886](https://github.com/ArkMowers/arknights-mower/pull/886) @Shawnsdaddy)
- 更新 CHANGELOG 至 4.1.5.6 ([#874](https://github.com/ArkMowers/arknights-mower/pull/874) @NiceAfternoon)
- 更新 CHANGELOG 和 游戏数据 ([#872](https://github.com/ArkMowers/arknights-mower/pull/872) @NiceAfternoon)
- changelog (@Shawnsdaddy)
- 4.1.6专精模块 ([#854](https://github.com/ArkMowers/arknights-mower/pull/854) @mikuzc)
- changelog ([#852](https://github.com/ArkMowers/arknights-mower/pull/852) @NiceAfternoon)
- 游戏资源 (@Shawnsdaddy)
- changelog (@Shawnsdaddy)
- UI (@Shawnsdaddy)
- max AP (@Shawnsdaddy)
- Deepseek option (@Shawnsdaddy)
- auto-nav update final draft (clean up later) (@Shawnsdaddy)
- add missing code (@Shawnsdaddy)
- dev_tools (@Shawnsdaddy)
- 4.1.5 ([#837](https://github.com/ArkMowers/arknights-mower/pull/837) @Shawnsdaddy @NiceAfternoon @Well2333)
- 🐳 添加 Dockerfile、docker-compose.yml 和相关构建脚本，支持 Mower 镜像构建与运行 ([#825](https://github.com/ArkMowers/arknights-mower/pull/825) @Well2333)
- add pic (@Shawnsdaddy)
- draft (@Shawnsdaddy)
- 4.1.0 ([#821](https://github.com/ArkMowers/arknights-mower/pull/821) @Shawnsdaddy @Anyk00 @eiHeyH)
- 4.1.1 ([#809](https://github.com/ArkMowers/arknights-mower/pull/809) @Shawnsdaddy @Anyk00 @eiHeyH)
- 2025.10.1 ([#800](https://github.com/ArkMowers/arknights-mower/pull/800) @Shawnsdaddy @djkcyl)
- 移除不必要的操作 (@Shawnsdaddy)
- 移除diy.py (@Shawnsdaddy)
- 提前跑单卡死 (@Shawnsdaddy)
- 扩展颜色识别范围 (@citydirector)
- Update get_number (@citydirector)
- #622 (@Shawnsdaddy)
- maa 调用退回主界面 (@Shawnsdaddy)
- fix 函数名typo (@Shawnsdaddy)
- #394 add new feature (@Shawnsdaddy)
- fix config not first load (@Shawnsdaddy)
- 加个catch 防止命令失败 (@Shawnsdaddy)
- 读基报等2秒动画 (@Shawnsdaddy)
- tool cmd update (@Shawnsdaddy)
- 结束后返回主界面 (@Shawnsdaddy)
- 会客室新家具支持 (@Shawnsdaddy)
- 施工完毕：九色鹿允许非基建材料垫刀 ([#779](https://github.com/ArkMowers/arknights-mower/pull/779) @HoverSoul)
- 修正：加工站任务的垫刀材料检查及添加报错提示 ([#777](https://github.com/ArkMowers/arknights-mower/pull/777) @HoverSoul)
- AI输出 改为流式 (@Shawnsdaddy)
- AI 添加FAQ工具 (@Shawnsdaddy)
- fix format (@Shawnsdaddy)
- 欢迎词 (@Shawnsdaddy)
- Add 读取数据库tool (@Shawnsdaddy)
- update requirement (@Shawnsdaddy)
- Agent ([#767](https://github.com/ArkMowers/arknights-mower/pull/767) @Shawnsdaddy)
- add submit issue tool (@Shawnsdaddy)
- 训练位放人 ([#759](https://github.com/ArkMowers/arknights-mower/pull/759) @Anyk00)
- init _agent (@Shawnsdaddy)
- 挤人上班时跳过回满改为跳过用尽回满 (@Anyk00)
- 允许通过本地图片训练识别模型 (@Anyk00)
- 清除宿舍信息前match (@Shawnsdaddy)
- 饼图工休比计算调整，调整为组内最低，同时点击组名按钮可以显示/隐藏全组干员工休比，饼图可拖拽，拖拽有做本地持久化 (@Suzuran-ley)
- bug fix (@Shawnsdaddy)
- 重新格式化了一下 (@Suzuran-ley)
- Revert "bugfix" (@Anyk00)
- 加工站任务防卡死 (@Shawnsdaddy)
- maa运行中截图 (@Shawnsdaddy)
- 扫描前刷新一次仓库 (@Shawnsdaddy)
- 如果有下班任务，则跳过纠错 (@Shawnsdaddy)
- 识别干员使用多线程加速 (@Anyk00)
- bugfix (@Anyk00)
- 合并设置时保持有序 (@Shawnsdaddy)
- bug fix (@Shawnsdaddy)
- fix format (@Shawnsdaddy)
- 更改版本号 (@qiuming2022)
- 增加Linux系统下的Docker一键部署 (@servis)
- #743 九色鹿支持 (@Shawnsdaddy)
- 添加Linux系统下python源码打包文件spec以及构建部署方法 (@servis)
- 在README.md中添加本地源码部署的教程 (@servis)
- fix typo (@Shawnsdaddy)
- #743 加入任务流 (@Shawnsdaddy)
- #743 仓库数据存入数据库 (@Shawnsdaddy)
- 添加maa连续战斗次数智能化，提高战斗效率 (@qiuming2022)
- 自动合成材料的初步实现 (@Shawnsdaddy)

**Full Changelog**: [2025.5.3.3...v4.1.6-alpha.1](https://github.com/ArkMowers/arknights-mower/compare/2025.5.3.3...v4.1.6-alpha.1)

## v4.1.5.8 - 2026-08-07

### 修复

- 修复 MAA 连通性检测误报
- 修复日志无输出的问题
- 修复专精 level 3 训练误插入换人任务的问题
- 专精升级改为读取倒计时成功后才标记 in_progress
- 修复活动关卡导航失败的问题
- 新增关卡体力消耗（AP）fallback 配置
- 修复 local operation 体力消耗为 None 导致的报错
- 游戏在后台时不强制退出，直接拉起前台
- MAA 配置缺失时友好降级
- 专精路线设置 - 默认值从JSON读取、自动保存、恢复默认修复

### 其他

- 更新游戏数据至SideStory `直到大地变为一颗酸橙`
- 优化打包体积

### 详细内容

#### 修复 fix

* 修复 mower 无法停止的问题（`/stop` 状态快照缺失字段导致接口报错） [#892](https://github.com/ArkMowers/arknights-mower/pull/892) [@ALEXsun0](https://github.com/ALEXsun0)

* 修复 Maa 连通性检测误报，补充启动前检查测试 [#901](https://github.com/ArkMowers/arknights-mower/pull/901) [@ALEXsun0](https://github.com/ALEXsun0)

* 修复专精调度、导航、日志等问题（训练时间读取真实倒计时、level 3 不再换人、导航失败、新增 AP fallback） [#902](https://github.com/ArkMowers/arknights-mower/pull/902) [@Shawnsdaddy](https://github.com/Shawnsdaddy)

* 修复专精路线设置默认值，专精计划改为从数据库读取 [#895](https://github.com/ArkMowers/arknights-mower/pull/895) [@Shawnsdaddy](https://github.com/Shawnsdaddy)

#### 清理 cleanup

* 删除 training_idle 死代码块与 half_off 剩余引用 [#895](https://github.com/ArkMowers/arknights-mower/pull/895) [@Shawnsdaddy](https://github.com/Shawnsdaddy)

#### 更新 update

* 更新游戏数据（新增干员机械师）及补充机械师基建技能描述 [#899](https://github.com/ArkMowers/arknights-mower/pull/899) [@WufeiHalf](https://github.com/WufeiHalf)

* 更新游戏数据，修复专精调度/导航/日志等问题 [#902](https://github.com/ArkMowers/arknights-mower/pull/902) [@Shawnsdaddy](https://github.com/Shawnsdaddy)

* 更新 CHANGELOG 至 4.1.5.8 并优化打包体积 [#903](https://github.com/ArkMowers/arknights-mower/pull/903) [@NiceAfternoon](https://github.com/NiceAfternoon)

## v4.1.5.7 - 2026-07-10

### 新增

- 新增 MAA 连通性测试与启动前检查
- 新增调用 MAA 刷生息演算，支持的主题有 `沙洲遗闻` 和 `重启锚点`
- 新增基建设置 `读取心情后先刷新副表`，开启后缓存清零重启会先读取心情并按载入心情数据模式自动重启，再触发副表和后续排班
- 新增启动游戏自定义命令选项，并预设唤醒无锁屏设备后启动游戏的命令
- 新增领取会客室信息板信用

### 修复

- 修复训练室空闲检测误判，优化全自动专精稳定性
- 优化全自动专精状态机，整合训练室状态检测到心情读取
- 统一任务间休眠收口，修复休息期间 /status 的 sleeping 状态
- 专精路线设置 - 默认值从JSON读取、自动保存、恢复默认修复

### 其他

- 更新游戏数据至故事集 `丛林症结`

### 详细内容

#### 新增 feat

* add MAA mac compatibility check [#877](https://github.com/ArkMowers/arknights-mower/pull/877) [@ALEXsun0](https://github.com/alexsun0)

* 初步实现调用 MAA 刷生息演算 [#878](https://github.com/ArkMowers/arknights-mower/pull/878) [@NiceAfternoon](https://github.com/NiceAfternoon)

* 新增缓存清零后刷新副表开关并修复训练室读取条件 [#881](https://github.com/ArkMowers/arknights-mower/pull/881) [@ALEXsun0](https://github.com/alexsun0)

* 新增启动游戏自定义命令选项 [#883](https://github.com/ArkMowers/arknights-mower/pull/883) [@ALEXsun0](https://github.com/alexsun0)

* 新增领取会客室信息板信用 [#885](https://github.com/ArkMowers/arknights-mower/pull/885) [@NiceAfternoon](https://github.com/NiceAfternoon)

#### 修复 fix

* 修复训练室空闲检测误判，优化全自动专精稳定性 [#875](https://github.com/ArkMowers/arknights-mower/pull/875) [@NiceAfternoon](https://github.com/NiceAfternoon)

* 优化全自动专精状态机，整合训练室状态检测到心情读取 [#880](https://github.com/ArkMowers/arknights-mower/pull/880) [@NiceAfternoon](https://github.com/NiceAfternoon)

* 统一任务间休眠收口，修复休息期间 /status 的 sleeping 状态 [#884](https://github.com/ArkMowers/arknights-mower/pull/884) [@djkcyl](https://github.com/djkcyl)

* 专精路线设置 - 默认值从JSON读取、自动保存、恢复默认修复 [#886](https://github.com/ArkMowers/arknights-mower/pull/886) [@Shawnsdaddy](https://github.com/Shawnsdaddy)

## 4.1.5.6

- 修复在无专精计划时重复添加加工站配置的问题
- 修复邮件发送基建报告时缺失龙舌兰赤金的问题
- 优化全自动专精功能
- 新增基建设置 `训练室协助位总是跟随排班`
- 新增自动合成配置的默认加工站干员设置
- 新增无专精计划时可使用自动合成配置添加全量材料合成配置
- 移除专精计划与排班表的冲突检测

详细内容：
### 新增 feat

- feat: 重构全自动专精调度、增加加工站干员配置并修复邮件和无法删除的加工配置问题 [(#873)@NiceAfternoon](https://github.com/ArkMowers/arknights-mower/commit/8a000046167caa90d40c9e526e98f6310d76ed0c)


## 4.1.5.5

- 新增全自动专精功能
- 优化合成方案配置
- 新增周计划关卡按开放时间过滤（活动期间可手动关闭）
- 在 基建报表 和 贸易订单分析 中增加可露希尔赤金
- 修复识别跑单订单价值时模板误匹配
- 仓库刷新逻辑优化
- 专精模块修复完善
- 更新游戏数据
- 网页文档中新增 专精推荐 和 Docker 部署

详细内容：
### 新增 feat

- feat: 完善全自动专精功能 [(#871)@NiceAfternoon](https://github.com/ArkMowers/arknights-mower/commit/2ee0cfd909c277ba5c978d4c2fa20a83ac313ac2)
- feat: 实现全自动专精功能并优化合成方案配置 [(#862)@mikuzc](https://github.com/ArkMowers/arknights-mower/commit/b54c7a89199fdf8e71731768a39c8be970564bef)
- feat: add Closure order in report and trade order analysis [(#865)@NiceAfternoon](https://github.com/ArkMowers/arknights-mower/commit/92c2cb2fc95043e816bdca1fbcdbfa2553269890)
- feat: 周计划关卡按开放时间过滤，活动期间可关闭 [(#860)@clousky2020](https://github.com/ArkMowers/arknights-mower/commit/42a8f6b9e8cdb0f4c662fd4c666dd47567225447)
- 4.1.6仓库刷新逻辑优化 [(#857)@mikuzc](https://github.com/ArkMowers/arknights-mower/commit/f72c81794102c27cbb762d7635c8181a3f7266fb)
- 4.1.6专精模块修复完善 [(#855)@mikuzc](https://github.com/ArkMowers/arknights-mower/commit/16e5a818a2119585237c4626f97cc4494243e2b3)

### 修复 fix

- fix: 修复识别跑单订单价值时模板误匹配 [(#858)@NiceAfternoon](https://github.com/ArkMowers/arknights-mower/commit/067aaffe3be283bf1baab27cf656635eb926560d)

### 文档 doc

- docs: 为 README 添加 Docker 部署文档链接 [(#866)@dhujsi](https://github.com/ArkMowers/arknights-mower/commit/612797cc15448bdabb02da1922642e9043ded839)
- 文档更新内容详见 [Commits - doc-pages](https://github.com/ArkMowers/arknights-mower/commits/doc-pages)


## 4.1.5.4

- 新增专精推荐模块
- 支持一图流干员练度导入
- 适配最大理智上限改为 210
- 新增专精推荐 Tab 页面
- 修复部分场景下的理智数据异常

详细内容：
### 新增 feat

- 专精推荐模块 [@Shawnsdaddy]
- 一图流干员练度导入 [@Shawnsdaddy]
- 4.1.6专精模块 [(#854)@mikuzc]

### 修复 fix

- 适配最大理智上限 210 [@Shawnsdaddy]

## 4.1.5.3

- 新增可露希尔跑单
- 处理闪断更新公告中不合法的结束时间
- 修复跑单订单类型识别不正确的问题
- 为新增的四种材料在仓库中分类
- 修复基建房间干员名称前缀匹配错误
- 防止用尽任务生成过期时间
- 领取奖励时跳过见习任务页检查

详细内容：
### 新增 feat
- 可露希尔跑单 [@Shawnsdaddy](https://github.com/ArkMowers/arknights-mower/commit/7ada670ab5050f9f2082da9f0289c0682a8ef729)

### 修复 fix
- 处理闪断更新公告中的 24:00 时间 [(#850)@clousky2020](https://github.com/ArkMowers/arknights-mower/commit/98e31804cb5b53c2116b3ffa902b2277535c4495)
- 修复 auto_get_res_new.py 中的解析逻辑，适配部分游戏数据字段从数字改为字符串 [(#849)@NiceAfternoon](https://github.com/ArkMowers/arknights-mower/commit/9071db83b10129037046715f581f7daca45e4c92)
- 修复跑单订单类型误判并适配新增材料分类 [(#851)@NiceAfternoon](https://github.com/ArkMowers/arknights-mower/commit/b6e23d2d93f09dd76597db53d66f96b87e267c4a)
- 修复房间干员识别、用尽任务时间和见习任务跳过 [(#848)@ALEXsun0](https://github.com/ArkMowers/arknights-mower/commit/1b2d9baff710aa5f8de2a8f1129de35b3980dbf4)

## 4.1.5.2
- 游戏数据更新
- 支持 可露希尔 跑单
- UI周计划更新（中文名字+开放日期显示）
- 新增解决验证码功能（需要设置MowerAI助手使用）
- 新增每日体力阈值功能
- 新增自动刷关（关卡自动导航需要设置MowerAI助手，否则可以在群里求导航路径配置文件在\tmp文件夹下）
- 新增版本改动信息提示
- AI助手输出内容支持 markdown 渲染
- 新增Deepseek深度思考选项
- 新增APIKEY后门（支持token.txt文件）
- 修复理智获取错误
- UI设置页面调整，大型任务移至获取信用及购物下方

## 4.1.5.1
- AI助手新增漏单分析工具
- 自动刷关软登录

## 4.1.5
- 游戏资源更新，新增多开命名显示，补充 Docker / 镜像构建相关支持。

## 4.1.4
- 游戏资源更新，新增森空岛终末地签到和测试签到功能。

## 4.1.3
- 资源更新。

## 4.1.2
- 修复提前跑单循环问题。

## 4.1.1
- 切换到 4.1.x 版本号体系，修复专精结算页面识别。

## 2025.10.1
- 游戏数据更新、识别图片更新、公招修复、兼容旧版 MuMu API，并清理部分无用操作。

## 2025.8.2.1
- 修复8.2 保活设置不触发问题
- UI修复DS 深度思考选项不显示
- 新增服务器维护期间提前跑单
- 新增服务器维护期间自动暂停任务

## 2025.8.2
- 九色鹿修复+优化
- 非工作站选人后心情排序移除（宿舍除外）
- 新增任务结束后台保活
- 读取基报2秒延时

## 2025.8.1
- 游戏资源更新

## 2025.7.3
- 游戏资源更新

## 2025.7.2
- 九色鹿合成修复了Key报错
- 游戏资源更新
- party时间小问题修复

## 2025.7.1.2
- AI新增了分析报错信息功能
- 多开器新增了一键全部启动
- 可能修复了加工站安排"Free"或者"Current"失败的bug（可是测下来可能还有其他问题）比如训练室房间是空会卡死，选人中间报错会卡死
- AI文本改为streaming

## 2025.7.1.1
- 把 7.1 没有加的训练室代码补进来了
- 训练位不可安排 3 星，或者技能未满级的 4 星以上干员（问 YJ 为什么）
- 训练位无法选择正在工作的干员
- AI更新了检索常见问题功能，内置了部分 FAQ 表（找不到可以反馈）
- 系统任务 + 报错存入数据库，以便以后用 AI 分析
- AI更新了防止乱问功能
- AI修复了找不到工具卡死的 bug

## 2025.7.1
- 清除宿舍信息前 match（修复莫名其妙纠错 bug）
- 允许通过本地图片训练识别模型
- MAAapi更新
- 用尽任务优化
- 挤人上班时跳过回满改为跳过用尽回满
- 本地文档复活
- 新增本地 AI 助手，目前仅接入 deepseek
- 仅在 party 时间过期或不存在时更新 op_data.party_time，以修复跃跃排班表失效
- 训练位放人
- 九色鹿逻辑判定修复
- 保全派驻导航更新

## 2025.6.3.1
- UI添加额外的报表分析+自定义产出
- 修复在某些条件下宿舍信息会丢失的bug
- 九色鹿字典报错修复

## 2025.6.3
- 新增MAA视J
- 仓库分类新增新材料
- 增加skd读取仓库材料频率
- 九色鹿计算点击修复
- 如果有未下完班任务，跳过纠错
- 合并副表优先级保持有序
- 九色鹿判定条件优化
- 加工任务新增防卡死机制（还未找到卡死bug root cause）

## 2025.6.2
- UI适配更新
- 新干员数据添加

## 2025.6.1.1
- 优化加工完截图时机
- 修复加工站概率卡死

## 2025.6.1
- 无缝材料合成支持九色鹿
- 修复了材料合成的已知bug

## 2025.5.5
- 无缝材料合成上线（九色鹿敬请期待）

## 2025.5.4.1
- 修复了仓库字典key报错
- 修复了材料中途不够导致的死循环

## 2025.5.4
- MAA连战支持（pikahan,qiuming2022）
- 无缝材料合成（暂不支持九色鹿）

## 2025.5.3.4
- 邮件发送订单报告修复
- 选人swipe计数时机修复
- 启动副表触发时机修复

## 2025.5.3.3
- UI截图设置加入缓存，图片url加入释放逻辑
- 职介选人前都会切一次ALL

## 2025.5.3.1beta
- 修正跑单时间时自动加速低级贸易站（如果未指定无人机贸易站）
- 选人时间如果略长（15s每个干员）则自动记录为使用职介筛选

## 2025.5.3
- 跑单自动加速低级无人机修复（Wei-png）

## 2025.5.3beta
- 基建跳转识别优化
- UI新增模拟器实时截图
- 切表自动清除宿舍优先级

## 2025.5.2
- ALL职介选择改成始终切ALL来规避YJbug【幸运104n,浮生泪】
- 除0报错【th.252_32贸...】
- 真实用尽在有组情况不触发

## 2025.5.1.1
- ALL职介选择优化【415470991】

## 2025.5.1
- 游戏新角色适配
- 职介筛选适配性更新

## 2025.4.2
- 邮件发送添加跑单信息
- 第一次启动自动切副表
- 中枢读取详细心情倒计时
- 重新更新了选人模型和元数据，请重新更新 4.2+ 资源

## 2025.4.1
- 新干员适配
- 修复不养闲人任务合并(Anyk00)
- 修复邮件发送时机(Anyk00)
- 修复重启游戏bug+优化添加专精任务(Anyk00)
- Maa导航api更新(Outsider225)

## 2025.3.1
- 新干员适配
- 发送时间revert

## 2025.2.3
- 修复了2.2的亿点点bug
- 邮件发送改为maa停止后
- 读取时间失败不再显示error

## 2025.2.2
- 计算上班时间根据条件移除 强制优先级(anykk00)
- Docker构建文件更新(frlda)
- 模拟器卡死重启修复
- 恢复提前8分钟上班(anykk00)
- 下班+排序任务合并
- 修复party检测不到时间问题
- UI修复宿舍优先级显示问题
- 更新新干员

## 2025.2.1
- UI新增急救心情阈值(anykk00)
- 替换组心情监视(anykk00)
- 无人机上限提升
- UI更新+maa领取奖励(anykk00)
- 联网增加30秒timeout时间，防止Mower卡死
- 释放不会增加过时任务【czt635】
- 宿舍移位优化（增加vip重排+自定义优先级）
- 新增自定义宿舍排序
- 减少进错房间重试次数

## 2025.1.4
- 重启线索功能

## 2025.1.3
- 适配游戏更新
- 暂时关闭线索功能
- 排班表添加活动室（UI）暂时不支持换人，没什么卵用的话以后会移除

## 2025.1.2
- 兼容老排班表如果低优先设置过多会排班出错（会报warning）【1121362417等】
- 修复若干小bug
- 用尽下班失败不会疯狂轰炸邮件
- 主班阿米娅下班无法被选择【2139689327】
- 选人二次确认修复【很多人】
- 后端移除部分最大分组数代码

## 2025.1.1
- 宿舍排序优化
- 正在激活的副表提醒【911804553】
- 强制弹性模式
- 弹性模式bug修复【1249033051】
- 新版maa调用修复【2768543172等】
- 保全导航超重绝缘水泥修复【1772532975】
- 反馈log添加版本信息+排班表

## 2024.12.5.3
- 修复在低帧率模式下，选人会失败
- 修复在宿舍移位撤回情况导致宿舍数据被纠错清除【911804553】

## 2024.12.5.2
- 修复用尽下班会去宿舍再读取一次下班时间

## 2024.12.5.1
- 修复代码拼写错误【3023094357】
- 弹性模式 跳过plan逻辑优化 【911804553】

## 2024.12.5
- 职介筛选配色阈值调低【1079159658】
- 保全导能单元选择更新 【1772532975】
- 修复弹性模式在某些情况不会生成 用尽 下班任务
- 弹性模式 用尽 增加极端情况报错
- MAA如果中途停止依旧发送部分掉落信息

## 2024.12.4
- 修复新增宿舍移位任务检查时机失效【923857607,1404766716等】
- 修复非当前宿舍宿管在前会找不到【3634223326】
- 修复某些特定情况下会出现两个相同人 【3634223326,491134959,1404766716】
- 修复某些场景会卡死邮箱（之前改动代码没有复制进增量包）【923857607等】
- 移除某些日志打印（yk00）
- 新增新逻辑的用尽处理（还没有机会测试）

## 2024.12.3
- 邮箱识别修复 + 自动清除已读邮件【很多人】
- 排班逻辑优化（在宿舍直接滑动到最后，如果滑动太远会直接切回第一页）
- 新增弹性休息模式，具体改动请去 UI 基建设置界面查看（半测试，建议先试用）：最大分组数失效，低优先逻辑变更为强制低优先，回满逻辑变更为强制回满，整体平均心情低于心情阈值 * 0.75 时休息阶段塞满宿舍，否则只安排满 vip 位
- 新增宿舍排序逻辑（高效组会自动往前挪），可能与旧的休息模式混用产生问题，后续会根据反馈继续修正
- 无人机跑单改为接收订单（原先是滑动）
- 任务执行排序按照工作站然后宿舍 1-4
- 保全任务导航更新【1772532975】
- 肉鸽新增分队

## 2024.12.2
- UI 邮箱设置增加时差修正
- 修复宿舍职介排序不触发

## 2024.12.1.1
- 更新游戏资源

## 2024.12.1
- 新增识别订单并且将数据存至数据库 支持一键导入老订单截图 UI订单分析移动
- 新增安排重复干员检查【3634223326】
- 用尽刷新修复【911804553】（未测试）
- 修复特定情况下的选人问题【3634223326】（半测试）

## 2024.11.2.2
- 修复部分设备职业筛选卡住
- 修复待办事项收取CD不工作+改成15分钟CD
- 新增非葛朗台跑单截图

## 2024.11.2.1
- 移除测试代码
- 更新CD逻辑防止卡住+CD改成30分钟

## 2024.11.2
- 新增用户反馈（邮件自动上传log）
- 收取基建通知加入2小时CD（防止误触）
- 修复filter 识别

## 2024.11.1.4
- 搬运仓库扫描
- 修复 干员选择时 影响多个工作站 无法确认
- 房间检查逻辑优化
- 修复菲亚任务+贸易站刷新 卡死（未测试）
- 修复不养闲人概率循环
- 改动记录倒序排序

## 2024.11.1.3
- 改动收取TODO 限制为一次（）防止重复点击成一键休息

## 2024.11.1.2
- 新增职介筛选
- 如果出现 bug 请反馈至频道
- 可以前往 \arknights_mower\data\arrange_order.json ，将「职介选择开关」替换成 [] 以关闭该功能

## 2024.11.1.1
- 新干员基地选择模型更新
- UI头像更新
- 深海组心情倒序(临时解决）

## 2024.11.1
- 游戏UI界面适配更新
- 更新后卡死的可以更改截图方式

## 2024.10.1.3
- 预测最短休息时间排除加工站干员
- 跑单截图优化
- 必须从 10.1.2 以上更新

## 2024.10.1.2
- 修复专精任务无法添加
- 修复不养闲人未排除黑名单
- 新增休息预测最低休息时间功能（半测试）：生成上班任务时，如果预计算有干员会在休息完毕前用尽，则会修改上班时间为用尽前半小时；只在心情自救模式不生效的时候触发

## 2024.10.1.1
- 修正了异格的选人识别+添加头像

## 2024.10.1
- 不养闲人模式现在会随时塞心情未达到上限的干员去休息了
- UI 更新：副表支持输入房间，拖拽自动更新【所有其他表】对应数据
- 跑单截图加回来了
- 尝试修复skd签到
- 还有其他用户体验优化
- UI【重要】附表支持前后移动（可以将全局副表向后移动，因为同时满足条件的情况排序靠后的副表会覆盖前面的副表）

## 2024.9.4
- 新增功能：不养闲人任务合并
- 新增功能：自定义副表名称
- 新增功能：信用作战指定编队
- 基建逻辑优化：仅回满干员在同组无用尽的情况下会提前上班，移除仅回满干员心情上限 -0.5
- 使用优化：UI 路径改动
- 使用优化：调用 Maa 刷日常时可以手动停止 Maa
- 使用优化：工具人数据加入缓存
