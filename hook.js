"use strict";

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
            
            // 拦截 show - 许可证窗口不显示
            var origShow = BW.prototype.show;
            BW.prototype.show = function() {
                if (this._isLicenseWindow) return;
                return origShow.apply(this, arguments);
            };
            
            // 拦截 loadURL - 标记许可证窗口
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
