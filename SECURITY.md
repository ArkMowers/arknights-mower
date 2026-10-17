# 安全政策 / Security Policy

## 中文

### 支持的版本

本项目仅对**最新正式版**提供安全支持。这里的“正式版”指非预发布版本的正式 Release。公测版（alpha）、开发版以及已被新版取代的旧正式版不单独提供安全修复；请升级到包含修复的最新正式版。每条安全公告会说明已确认的受影响版本和首个修复版本。旧版本不受支持，并不表示它们不受漏洞影响。

### 私密报告安全漏洞

如果仓库的 **Security → Advisories** 页面提供 **Report a vulnerability** 入口，请通过该入口提交私密报告。若入口尚未开放，请先联系仓库维护者商定私密沟通方式。请不要在公开 Issue、Discussion、群聊或社交平台发布尚未修复的漏洞细节、利用代码或真实凭据。

报告中请尽量提供：

- 受影响的版本、操作系统和部署方式（源码、独立安装包或 Docker）；
- 攻击者需要具备的访问条件，以及预期行为与实际行为；
- 可在测试环境复现的最小步骤、相关代码位置和影响说明；
- 已脱敏的日志、截图或请求记录。请勿提交真实密码、令牌、个人数据或完整用户配置。

### 处理与披露

维护者会核对报告、评估影响范围并协调修复。修复和升级方案明确后，维护者可发布安全公告，并与报告者协调披露时间及署名。是否申请 CVE 取决于漏洞性质和编号机构的审核结果。

### 安全边界

本政策适用于本仓库维护的应用代码、Web 界面与接口、自动化能力、配置与凭据处理、更新流程，以及随仓库提供的部署配置。安全问题应说明真实可达的使用场景和信任边界；仅有危险函数或过期依赖的存在，不足以单独证明用户受到影响。

未经授权的客户端不应读取用户数据、调用受保护的自动化能力或取得本地凭据。处理外部输入、下载内容和本地文件时，应限制在预期的权限与路径范围内。

## English

### Supported versions

Security support is provided only for the **latest stable release**. A stable release is a non-prerelease Release. Alpha builds, development builds, and older stable releases do not receive separate security backports; please upgrade to the latest stable release containing the fix. Each security advisory will identify the confirmed affected versions and the first fixed version. An unsupported version may still be affected by a vulnerability.

### Privately reporting a vulnerability

If **Report a vulnerability** is available under **Security → Advisories** in this repository, use it to submit a private report. Otherwise, contact the maintainers first to arrange a private reporting channel. Do not post details of an unpatched vulnerability, exploit code, or real credentials in a public Issue, Discussion, chat group, or social media post.

Please include, when possible:

- The affected version, operating system, and deployment method (source, standalone package, or Docker);
- The access an attacker needs, and the expected and observed behavior;
- Minimal reproduction steps in a test environment, relevant code locations, and the impact;
- Redacted logs, screenshots, or request records. Do not submit real passwords, tokens, personal data, or complete user configuration files.

### Handling and disclosure

Maintainers will review the report, assess its scope, and coordinate a fix. Once a fix and upgrade path are clear, maintainers may publish a security advisory and coordinate disclosure timing and credit with the reporter. CVE assignment depends on the nature of the vulnerability and review by the relevant numbering authority.

### Security boundary

This policy covers application code maintained in this repository, the Web UI and APIs, automation features, configuration and credential handling, update mechanisms, and deployment configuration shipped with the repository. Reports should explain a realistic reachable scenario and the trust boundary crossed. The presence of a dangerous function or outdated dependency alone does not establish user impact.

Unauthorized clients must not be able to read user data, invoke protected automation, or obtain local credentials. External input, downloaded content, and local files must be handled within their intended permissions and path boundaries.
