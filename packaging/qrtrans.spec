# -*- mode: python ; coding: utf-8 -*-
# QRTrans Windows 单 exe 打包配置（也兼容 Linux 本地冒烟构建）
# libzbar 的 DLL 由 pyzbar 的 Windows wheel 自带；这里显式收集，
# 因为 pyinstaller-hooks-contrib 中不存在 pyzbar hook（已核实）。
from PyInstaller.utils.hooks import collect_dynamic_libs, collect_submodules
import os

# spec 位于 packaging/ 下；入口与 imports 均相对于项目根解析
PROJECT_ROOT = os.path.abspath(os.path.join(SPECPATH, '..'))

binaries = collect_dynamic_libs('pyzbar')   # Windows: libzbar-64.dll, libiconv.dll
hiddenimports = (
    collect_submodules('pyzbar')
    + collect_submodules('qrcode')
    + ['PIL']
)

a = Analysis(
    [os.path.join(SPECPATH, 'entry.py')],
    pathex=[PROJECT_ROOT],
    binaries=binaries,
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='qrtrans',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                  # UPX 常引发杀软误报，关闭
    runtime_tmpdir=None,
    console=True,               # CLI 工具保留控制台
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
