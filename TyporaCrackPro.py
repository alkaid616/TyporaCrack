#!/usr/bin/env python3
"""
Typora 增强版破解脚本 (七层保护 + 三层防御纵深)

基于 TyporaCrack.py (ASAR 重打包) + TyporaActivator.exe 分析改进

新增改进 (来源: TyporaActivator.exe 逆向分析):
  1. SLicense 注册表写入 — 即使 hook 失效也不会立刻弹窗
  2. 续期日期 trick — 日期设 2036 年，数据层面绕过 12h 续期检查
  3. 网络三重拦截 — DNS + net.request + fetch 全方位阻断

用法:
    python TyporaCrackPro.py <Typora路径>           # 部署
    python TyporaCrackPro.py <Typora路径> --restore # 恢复
    python TyporaCrackPro.py <Typora路径> --token   # 仅写入注册表 (不改 ASAR)
"""

import os
import sys
import json
import shutil
import subprocess
import hashlib
import uuid
import random
import time

# ============================================================
# 路径解析
# ============================================================

def get_typora_path():
    """获取 Typora 路径: 参数 > 脚本所在目录"""
    for arg in sys.argv[1:]:
        if not arg.startswith("-"):
            return arg
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if os.path.isfile(os.path.join(script_dir, "resources", "app.asar")):
        return script_dir
    return None


RESTORE = "--restore" in sys.argv
TOKEN_ONLY = "--token" in sys.argv
TYPORA_PATH = get_typora_path()

if not TYPORA_PATH:
    print("[-] Typora path not specified.")
    print("    Usage: python TyporaCrackPro.py <Typora路径>")
    print("    Example: python TyporaCrackPro.py D:\\Typora")
    print("    Or place this script in Typora directory.")
    sys.exit(1)

if not os.path.isdir(TYPORA_PATH):
    print(f"[-] Path not found: {TYPORA_PATH}")
    sys.exit(1)

RESOURCES = os.path.join(TYPORA_PATH, "resources")
APP_ASAR = os.path.join(RESOURCES, "app.asar")
APP_ASAR_BAK = APP_ASAR + ".bak"
EXTRACT_DIR = os.path.join(RESOURCES, "_bypass_tmp")


# ============================================================
# 注册表操作 (改进来源: TyporaActivator.exe)
# ============================================================

LICENSE_CHARSET = 'L23456789ABCDEFGHJKMNPQRSTUVWXYZ'


def generate_license():
    """
    生成 License 密钥 (格式 XXXXXX-XXXXXX-XXXXXX-XXXXXX)
    来源: TyporaActivator.exe 的 generate_license 函数
    字符集: 去除容易混淆的 I/O/Q/1/0
    """
    raw = ''.join(random.choice(LICENSE_CHARSET) for _ in range(22))
    # 2 个校验字符
    checksum = ''
    for n in range(2):
        s = sum(LICENSE_CHARSET.index(raw[n + i]) for i in range(0, 22, 2))
        s %= len(LICENSE_CHARSET)
        checksum += LICENSE_CHARSET[s]
    full = raw + checksum
    return '-'.join([full[0:6], full[6:12], full[12:18], full[18:24]])


def write_slicense_registry():
    """
    写入 SLicense 到注册表

    改进说明:
      原方案完全不碰注册表，依赖 app.quit hook 阻止退出。
      TyporaActivator.exe 分析发现 SLicense 格式: token#failCount#date
      日期设 2036 年 (10 年后)，renewLicense 计算 now - lastRetry
      得到负数，永远小于 12h，从数据层面绕过续期检查。

    收益: 即使 hook 失效，Typora 也不会立刻弹窗或清除激活状态。
    成本: 几行注册表写入代码。
    """
    try:
        import winreg
    except ImportError:
        print("[!] winreg 不可用 (非 Windows?)")
        return False

    # 检查是否已存在
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Typora')
        val, _ = winreg.QueryValueEx(key, 'SLicense')
        winreg.CloseKey(key)
        if val:
            print(f"[*] SLicense 已存在: {val[:50]}...")
            return True
    except FileNotFoundError:
        pass
    except Exception:
        pass

    # 生成一个格式正确的 SLicense
    # 不需要真实 AES 加密，因为 publicDecrypt hook 会伪造返回值
    # 但格式必须正确: token#failCount#date
    fake_token = 'A' * 64  # 占位 token
    fail_count = 0
    # 关键: 日期设 2036 年，lastRetry 始终是未来时间
    # renewLicense 检查 now - lastRetry < 12h，负数永远通过
    future_date = '1/1/2036'
    slicense_value = f'{fake_token}#{fail_count}#{future_date}'

    try:
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Typora')
        winreg.SetValueEx(key, 'SLicense', 0, winreg.REG_SZ, slicense_value)
        winreg.CloseKey(key)
        print(f"[+] SLicense 写入成功: {slicense_value[:50]}...")
        return True
    except Exception as e:
        print(f"[!] SLicense 写入失败: {e}")
        return False


# ============================================================
# Hook 代码 (合并 TyporaCrack + TyporaActivator 改进)
# ============================================================

HOOK_JS = r'''"use strict";

process.on('uncaughtException', function() {});

var Module = require("module");
var _origLoad = Module._load;
var _blocked = true;
var _isLicenseWin = false;

Module._load = function(request, parent, isMain) {
    var result = _origLoad.apply(this, arguments);

    if (request === 'electron' && result && !result._hooked) {
        if (result.app) {
            var app = result.app;
            var gotLock = app.requestSingleInstanceLock();
            if (gotLock) {
                // 主实例: 5秒内阻止退出 (完整性校验期间)
                app.quit = function() { if (!_blocked) process.exit(0); };
                app.exit = function() { if (!_blocked) process.exit(0); };
                app.on('before-quit', function(e) {
                    if (_blocked) e.preventDefault();
                    else process.exit(0);
                });
                setTimeout(function() { _blocked = false; }, 5000);
            }
        }

        // 拦截 license.show IPC
        if (result.ipcMain) {
            var h = result.ipcMain.handle;
            result.ipcMain.handle = function(ch, fn) {
                if (ch === 'license.show' || ch === 'license.show.debug')
                    return h.call(this, ch, function() { return {success:true}; });
                return h.apply(this, arguments);
            };
        }
        if (result.ipcRenderer) {
            var iv = result.ipcRenderer.invoke;
            result.ipcRenderer.invoke = function(ch) {
                if (ch === 'license.show' || ch === 'license.show.debug')
                    return Promise.resolve({success:true});
                return iv.apply(this, arguments);
            };
        }

        // 阻止许可证窗口显示
        if (result.BrowserWindow) {
            var BW = result.BrowserWindow;

            var origShow = BW.prototype.show;
            BW.prototype.show = function() {
                if (this._isLicenseWindow) return;
                return origShow.apply(this, arguments);
            };

            var origLoadURL = BW.prototype.loadURL;
            BW.prototype.loadURL = function(url) {
                if (url && url.indexOf('license.html') !== -1) {
                    this._isLicenseWindow = true;
                    return origLoadURL.call(this, 'about:blank');
                }
                return origLoadURL.apply(this, arguments);
            };
        }

        // ---- 改进: 网络三重拦截 (来源: TyporaActivator.exe) ----
        // 1. DNS 拦截: typora 域名 → 127.0.0.1
        try {
            var _dns = require('dns'), _dl = _dns.lookup;
            _dns.lookup = function(h, o, cb) {
                if (typeof h === 'string' && /typora/.test(h)) {
                    if (typeof o === 'function') return o(null, '127.0.0.1', 4);
                    if (typeof cb === 'function') return cb(null, '127.0.0.1', 4);
                    return;
                }
                return _dl.apply(this, arguments);
            };
        } catch(e) {}

        // 2. net.request 拦截 (在 electron 模块加载时)
        // 3. fetch 拦截 (在 Module._load 中拦截)
        // 这两个在下方通过 Module._load 的通用拦截实现

        result._hooked = true;
    }

    // ---- 改进: 通用网络请求拦截 ----
    try {
        // 拦截 electron net.request
        if (request === 'electron' && result && result.net) {
            var _nr = result.net.request;
            if (_nr && !_nr._hooked) {
                result.net.request = function(opts) {
                    var u = typeof opts === 'string' ? opts : (opts && (opts.url || opts.hostname || opts.host) || '');
                    if (/typora/.test(u)) {
                        var c = _nr.apply(this, arguments);
                        setTimeout(function() { try { c.emit('error', new Error('blocked')); } catch(e) {} }, 10);
                        return c;
                    }
                    return _nr.apply(this, arguments);
                };
                result.net.request._hooked = true;
            }
        }

        // 拦截 fetch
        if (typeof request === 'string' && request.indexOf('fetch') !== -1 && result) {
            var _t = typeof result === 'function' ? result : (result.default && typeof result.default === 'function' ? result.default : null);
            if (_t && !_t._hooked) {
                var _of = _t;
                var wrap = function(url, opts) {
                    var us = typeof url === 'string' ? url : (url && (url.url || url.href) || '');
                    if (/typora/.test(us)) {
                        return Promise.resolve({ok:false, status:403, json:function(){return Promise.resolve({})}, text:function(){return Promise.resolve('blocked')}});
                    }
                    return _of.apply(this, arguments);
                };
                wrap._hooked = true;
                if (typeof result !== 'function') {
                    result.default = wrap;
                } else {
                    Object.keys(result).forEach(function(k) { wrap[k] = result[k]; });
                    arguments[0] = wrap;
                }
            }
        }
    } catch(e) {}

    return result;
};

require("./launch.dist.js");
'''


# ============================================================
# ASAR 操作
# ============================================================

def backup():
    if not os.path.exists(APP_ASAR_BAK):
        print("[+] Backup app.asar -> app.asar.bak")
        shutil.copy2(APP_ASAR, APP_ASAR_BAK)
    else:
        print("[*] Backup exists")


def cleanup():
    if os.path.exists(EXTRACT_DIR):
        shutil.rmtree(EXTRACT_DIR)


def deploy():
    print("=" * 55)
    print("  Typora Enhanced Crack (7-Layer + 3-Defense)")
    print("=" * 55)
    print()

    if not os.path.exists(APP_ASAR):
        print(f"[-] app.asar not found: {APP_ASAR}")
        return 1

    try:
        # 第 1 步: 写入注册表 (数据层防御)
        print("[Step 1/4] 写入注册表 SLicense ...")
        write_slicense_registry()
        print()

        if TOKEN_ONLY:
            print("[+] Token-only 模式，跳过 ASAR 修改")
            return 0

        # 第 2 步: 备份
        print("[Step 2/4] 备份 app.asar ...")
        backup()
        print()

        # 第 3 步: 解压 → 注入 → 重打包
        print("[Step 3/4] 构建 ASAR ...")

        # Extract
        print("  [+] Extracting app.asar ...")
        if os.path.exists(EXTRACT_DIR):
            shutil.rmtree(EXTRACT_DIR)
        subprocess.run(
            ['npx', 'asar', 'extract', APP_ASAR_BAK, EXTRACT_DIR],
            capture_output=True, text=True, shell=True
        )
        if not os.path.exists(EXTRACT_DIR):
            print("  [-] Extract failed")
            return 1

        # Write hook.js
        print("  [+] Writing hook.js ...")
        with open(os.path.join(EXTRACT_DIR, "hook.js"), 'w', encoding='utf-8') as f:
            f.write(HOOK_JS)

        # Modify package.json
        pkg = os.path.join(EXTRACT_DIR, "package.json")
        with open(pkg, 'r') as f:
            data = json.load(f)
        data['main'] = 'hook.js'
        with open(pkg, 'w') as f:
            json.dump(data, f, indent=2)
        print("  [+] package.json main -> hook.js")

        # Pack
        print("  [+] Packing ASAR ...")
        temp_asar = APP_ASAR + ".tmp"
        result = subprocess.run(
            ['npx', 'asar', 'pack', EXTRACT_DIR, temp_asar],
            capture_output=True, text=True, shell=True
        )
        if result.returncode != 0:
            print(f"  [-] Pack failed: {result.stderr}")
            cleanup()
            return 1

        # Replace
        if os.path.exists(APP_ASAR):
            os.remove(APP_ASAR)
        shutil.copy2(temp_asar, APP_ASAR)
        os.remove(temp_asar)

        cleanup()
        print()

        # 第 4 步: 完成
        print("[Step 4/4] 完成")
        print()
        print("=" * 55)
        print("  DONE. Restart Typora.")
        print()
        print("  已启用:")
        print("    [+] ASAR 重打包 (完整性哈希自然匹配)")
        print("    [+] SLicense 注册表写入 (2036 年到期)")
        print("    [+] DNS 拦截 (typora 域名 -> 127.0.0.1)")
        print("    [+] net.request 拦截 (Electron 网络请求)")
        print("    [+] fetch 拦截 (JS fetch 请求)")
        print("    [+] license.show IPC 拦截")
        print("    [+] 许可证窗口隐藏")
        print("    [+] 多实例支持")
        print()
        print(f"  Restore: python {os.path.basename(__file__)} <path> --restore")
        print("=" * 55)
        return 0

    except Exception as e:
        print(f"[-] Error: {e}")
        import traceback
        traceback.print_exc()
        cleanup()
        return 1


def restore():
    if os.path.exists(APP_ASAR_BAK):
        print("[+] Restoring app.asar.bak -> app.asar ...")
        shutil.copy2(APP_ASAR_BAK, APP_ASAR)
        print("[+] Restored.")
    else:
        print("[-] No backup found.")


if __name__ == "__main__":
    print(f"[*] Typora path: {TYPORA_PATH}")
    if RESTORE:
        restore()
    else:
        sys.exit(deploy())
