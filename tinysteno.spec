# PyInstaller build spec for TinySteno.
#
#   py -m PyInstaller tinysteno.spec --noconfirm     -> one 48 MB exe, ~1.1 s cold start
#   set TINYSTENO_ONEDIR=1 && py -m PyInstaller tinysteno.spec --noconfirm
#                                                    -> a 120 MB folder, ~0.4 s start
#
# Single file is the default because the size and startup difference is small here. That
# is only true because of the exclude list below: PySide6 ships roughly a quarter of a
# gigabyte of modules and this app imports just QtCore, QtGui and QtWidgets. A default
# PySide6 onefile build is typically 150 MB+ and takes several seconds to unpack.

import os

ONEFILE = os.environ.get("TINYSTENO_ONEDIR") != "1"

# Qt modules the trainer never imports. WebEngine alone is over half the payload.
EXCLUDED_QT = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel", "PySide6.QtWebSockets", "PySide6.QtWebView",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic", "PySide6.Qt3DAnimation", "PySide6.Qt3DExtras",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtGraphs",
    "PySide6.QtGraphsWidgets",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtSpatialAudio",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets",
    "PySide6.QtQuickControls2", "PySide6.QtQuick3D", "PySide6.QtQuickTest",
    "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtPositioning",
    "PySide6.QtLocation", "PySide6.QtSerialBus", "PySide6.QtRemoteObjects",
    "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtHelp", "PySide6.QtDesigner",
    "PySide6.QtUiTools", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    "PySide6.QtSensors", "PySide6.QtScxml", "PySide6.QtStateMachine",
    "PySide6.QtTextToSpeech", "PySide6.QtHttpServer", "PySide6.QtNetworkAuth",
    "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets",
]

# Stdlib and third-party packages PyInstaller otherwise drags in speculatively.
EXCLUDED_OTHER = [
    "tkinter", "unittest", "pydoc_data", "lib2to3", "distutils",
    "numpy", "PIL", "matplotlib", "pytest", "setuptools", "pip",
]

a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=[],
    # The icon is embedded in the exe for Explorer, but Qt needs its own copy to set the
    # window and taskbar icon at runtime.
    datas=[("assets/tinysteno.ico", "assets")],
    # pyserial resolves the platform backend by import inside serial.tools.list_ports;
    # naming it explicitly keeps port scanning working in the frozen build.
    hiddenimports=["serial.tools.list_ports_windows"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDED_QT + EXCLUDED_OTHER,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe_kwargs = dict(
    name="TinySteno",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,               # GUI app: no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/tinysteno.ico",
    version="version_info.txt",
)

if ONEFILE:
    exe = EXE(
        pyz, a.scripts, a.binaries, a.datas, [],
        exclude_binaries=False,
        runtime_tmpdir=None,
        **exe_kwargs,
    )
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **exe_kwargs)
    coll = COLLECT(
        exe, a.binaries, a.datas,
        strip=False, upx=False, name="TinySteno",
    )
