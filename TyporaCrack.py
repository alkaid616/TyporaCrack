#!/usr/bin/env python3
"""
Typora 1.13.7 单文件破解脚本

无需额外文件，直接运行即可部署/恢复。

用法:
    python deploy_standalone.py           # 部署
    python deploy_standalone.py --restore # 恢复
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

HOOK_JS = r'''"use strict";

process.on('uncaughtException', function() {});

var Module = require("module");
var _origLoad = Module._load;
var _blocked = true;

Module._load = function(request, parent, isMain) {
    var result = _origLoad.apply(this, arguments);

    if (request === 'electron' && result && !result._hooked) {
        if (result.app) {
            var app = result.app;
            var gotLock = app.requestSingleInstanceLock();
            if (gotLock) {
                app.quit = function() { if (!_blocked) process.exit(0); };
                app.exit = function() { if (!_blocked) process.exit(0); };
                app.on('before-quit', function(e) {
                    if (_blocked) e.preventDefault();
                    else process.exit(0);
                });
                setTimeout(function() { _blocked = false; }, 5000);
            }
        }

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

        result._hooked = true;
    }

    return result;
};

require("./launch.dist.js");
'''


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
    print("  Typora 1.13.7 - Single File Bypass")
    print("=" * 55)

    if not os.path.exists(APP_ASAR):
        print(f"[-] app.asar not found: {APP_ASAR}")
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

        # Write hook.js
        print("[+] Writing hook.js ...")
        with open(os.path.join(EXTRACT_DIR, "hook.js"), 'w', encoding='utf-8') as f:
            f.write(HOOK_JS)

        # Modify package.json
        pkg = os.path.join(EXTRACT_DIR, "package.json")
        with open(pkg, 'r') as f:
            data = json.load(f)
        data['main'] = 'hook.js'
        with open(pkg, 'w') as f:
            json.dump(data, f, indent=2)
        print("[+] package.json main -> hook.js")

        # Pack
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
        print(f"[+] Restore: python {os.path.basename(__file__)} --restore")
        return 0

    except Exception as e:
        print(f"[-] Error: {e}")
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
    if len(sys.argv) > 1 and sys.argv[1] == "--restore":
        restore()
    else:
        sys.exit(deploy())
