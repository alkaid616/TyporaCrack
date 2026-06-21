#!/usr/bin/env python3
"""
Typora 1.13.7 - 七层保护链完整绕过

保护层:
  ① 启动层: package.json main → hook.js
  ② 完整性校验: uncaughtException 捕获 + app.quit 阻止
  ③ 许可证验证: Module._load 拦截 electron 模块
  ④ 试用期检查: (由 app.quit hook 阻止退出)
  ⑤ 续期机制: (由 app.quit hook 阻止退出)
  ⑥ 页面显示: ipcMain.handle/ipcRenderer.invoke 拦截
  ⑦ 错误处理: process.exit + app.quit + before-quit + BrowserWindow.loadURL

关键发现:
  - npx asar pack 自动计算正确的完整性哈希
  - Module._load 比 Module.prototype.require 更可靠
  - app.quit 必须 hook 以阻止完整性校验失败后的退出

用法:
    python deploy.py           # 部署
    python deploy.py --restore # 恢复
"""

import os
import sys
import json
import shutil
import subprocess

TYPORA_PATH = r"D:\Typora"
RESOURCES = os.path.join(TYPORA_PATH, "resources")
APP_ASAR = os.path.join(RESOURCES, "app.asar")
APP_ASAR_BAK = APP_ASAR + ".bak"
EXTRACT_DIR = os.path.join(RESOURCES, "_bypass_tmp")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HOOK_SOURCE = os.path.join(SCRIPT_DIR, "hook.js")


def backup():
    if not os.path.exists(APP_ASAR_BAK):
        print("[+] Backup app.asar -> app.asar.bak")
        shutil.copy2(APP_ASAR, APP_ASAR_BAK)
    else:
        print("[*] Backup exists")


def deploy():
    print("=" * 55)
    print("  Typora 1.13.7 - 7-Layer Protection Bypass")
    print("=" * 55)

    if not os.path.exists(APP_ASAR):
        print(f"[-] app.asar not found: {APP_ASAR}")
        return 1

    if not os.path.exists(HOOK_SOURCE):
        print(f"[-] hook.js not found: {HOOK_SOURCE}")
        return 1

    try:
        backup()

        # Extract
        print("[+] Extracting app.asar ...")
        if os.path.exists(EXTRACT_DIR):
            shutil.rmtree(EXTRACT_DIR)
        subprocess.run(
            ['npx', 'asar', 'extract', APP_ASAR_BAK, EXTRACT_DIR],
            capture_output=True, text=True, shell=True
        )
        if not os.path.exists(EXTRACT_DIR):
            print("[-] Extract failed")
            return 1

        # Inject hook.js
        print("[+] Injecting hook.js ...")
        shutil.copy2(HOOK_SOURCE, os.path.join(EXTRACT_DIR, "hook.js"))

        # Modify package.json
        pkg = os.path.join(EXTRACT_DIR, "package.json")
        with open(pkg, 'r') as f:
            data = json.load(f)
        data['main'] = 'hook.js'
        with open(pkg, 'w') as f:
            json.dump(data, f, indent=2)
        print("[+] package.json main -> hook.js")

        # Pack with npx asar (computes correct integrity hashes)
        print("[+] Packing ASAR ...")
        temp_asar = APP_ASAR + ".tmp"
        result = subprocess.run(
            ['npx', 'asar', 'pack', EXTRACT_DIR, temp_asar],
            capture_output=True, text=True, shell=True
        )
        if result.returncode != 0:
            print(f"[-] Pack failed: {result.stderr}")
            cleanup()
            return 1

        # Replace
        if os.path.exists(APP_ASAR):
            os.remove(APP_ASAR)
        shutil.copy2(temp_asar, APP_ASAR)
        os.remove(temp_asar)

        cleanup()

        print()
        print("[+] DONE. Restart Typora.")
        print(f"[+] Restore: python {__file__} --restore")
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


def cleanup():
    if os.path.exists(EXTRACT_DIR):
        shutil.rmtree(EXTRACT_DIR)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--restore":
        restore()
    else:
        sys.exit(deploy())
