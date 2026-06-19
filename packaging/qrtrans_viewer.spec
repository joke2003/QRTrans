# -*- mode: python ; coding: utf-8 -*-
# qrtrans-viewer 独立全屏播放器（Tkinter + Pillow，windowed，不弹控制台）
import os
from PyInstaller.utils.hooks import collect_submodules

PROJECT_ROOT = os.path.abspath(os.path.join(SPECPATH, '..'))
hiddenimports = (
    collect_submodules('PIL')
    + ['tkinter', 'PIL.ImageTk',
       'qrtrans_viewer', 'qrtrans_viewer.gui', 'qrtrans_viewer.core', 'qrtrans_viewer.__main__']
)

a = Analysis(
    [os.path.join(SPECPATH, 'entry_viewer.py')],
    pathex=[PROJECT_ROOT],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['qrtrans'],   # viewer 不耦合主包
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
    name='qrtrans-viewer',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    runtime_tmpdir=None, console=False,   # windowed：不弹控制台黑窗
    disable_windowed_traceback=False, argv_emulation=False,
    target_arch=None, codesign_identity=None, entitlements_file=None, icon=None,
)
