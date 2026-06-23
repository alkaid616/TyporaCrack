# TyporaCrack

Typora 1.13.7 许可证绕过工具。通过注入 hook.js 到 app.asar，拦截七层保护机制实现激活。

## 使用方法

### 方式一: 增强版 (推荐)

`TyporaCrackPro.py` 整合了 TyporaActivator.exe 逆向分析的改进，新增注册表写入和网络拦截：

```bash
python TyporaCrackPro.py D:\Typora            # 完整部署
python TyporaCrackPro.py D:\Typora --token    # 仅写注册表 (不改 ASAR)
python TyporaCrackPro.py D:\Typora --restore  # 恢复
```

### 方式二: 指定 Typora 路径

```bash
python deploy.py D:\Typora            # 部署
python deploy.py D:\Typora --restore  # 恢复
```

### 方式三: 将脚本放入 Typora 目录

将 `deploy.py` + `hook.js` 复制到 Typora 根目录，直接运行：

```bash
cd D:\Typora
python deploy.py
python deploy.py --restore
```

### 方式四: 单文件脚本 (无需 hook.js)

`TyporaCrack.py` 内嵌 hook.js，无需额外文件：

```bash
python TyporaCrack.py D:\Typora
python TyporaCrack.py D:\Typora --restore
```

## 仓库结构

```
TyporaCrack/
├── TyporaCrackPro.py  # 增强版 (推荐，含注册表+网络拦截)
├── TyporaCrack.py     # 单文件破解脚本 (无需额外文件)
├── hook.js            # 核心绕过 hook (98行)
├── deploy.py          # 部署/恢复脚本 (需要 hook.js)
├── docs/
│   └── analysis.md    # 完整逆向分析报告
├── README.md          # 本文档
└── .gitignore
```

## 工作原理

### 七层保护链

```
① 启动层    launch.dist.js 加载 V8 字节码
② 完整性    Electron 原生 SHA256 校验 ASAR 文件哈希
③ 许可证    RSA publicDecrypt 解密许可证密钥
④ 试用期    注册表 IDate + profile.data._iD
⑤ 续期      每12小时请求 api/client/activate
⑥ 页面      IPC license.show 显示许可证窗口
⑦ 退出      app.quit() → before-quit 事件链
```

### 绕过方法

| 层 | 保护 | 绕过 |
|---|------|------|
| ① | V8 字节码加载 | 改 package.json main → hook.js |
| ② | SHA256 校验 | npx asar pack 自动计算正确哈希 |
| ③ | RSA 解密 | Module._load 拦截 |
| ④ | 试用期 | app.quit hook 阻止退出 |
| ⑤ | 续期 | app.quit hook 阻止退出 + SLicense 日期 trick |
| ⑥ | license.show | IPC 拦截 + BrowserWindow.show 拦截 |
| ⑦ | app.quit | process.exit(0) + before-quit preventDefault |

### 增强版额外防御 (TyporaCrackPro.py)

| 防御层 | 来源 | 说明 |
|--------|------|------|
| SLicense 注册表 | TyporaActivator.exe 逆向 | 写入格式正确的 SLicense，日期设 2036 年，续期检查永远通过 |
| DNS 拦截 | TyporaActivator.exe 逆向 | typora 域名重定向到 127.0.0.1 |
| net.request 拦截 | TyporaActivator.exe 逆向 | Electron 网络请求阻断 |
| fetch 拦截 | TyporaActivator.exe 逆向 | JS fetch 请求返回 403 |

### 关键发现

- `Module._load` 比 `Module.prototype.require` 更可靠（拦截 `reqnode` 调用）
- `process.exit` hook 无效，必须 hook `app.quit`
- Electron fuse 禁用了 `NODE_OPTIONS`，无法通过环境变量注入
- `npx asar pack` 自动计算正确的完整性哈希
- `requestSingleInstanceLock` 区分主/辅助实例
- SLicense 日期设远未来可从数据层面绕过 12h 续期检查（来源: TyporaActivator.exe 逆向）
- 网络拦截需 DNS + net.request + fetch 三重防护，防止未来版本改用其他协议

## 免责声明

本项目仅供学习交流使用。请支持正版软件。

Typora 官网: https://typora.io
