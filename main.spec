# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    # data/ 폴더째 넣으면 재배포 금지 자료(감성사전, 평가 세트)까지 실행 파일에 들어가므로, 앱에 필요한 신조어 사전만 넣습니다.
    # 감성사전은 실행 파일 옆 data/sentiment.json에서 읽고, 없으면 감성사전 없이 판독합니다.
    # 감성사전 단어를 찾는 형태소 분석기(kiwipiepy)의 모델 파일은 함께 넣습니다.
    datas=[('emotions', 'emotions'), ('data/neologisms.json', 'data')] + collect_data_files('kiwipiepy_model'),
    hiddenimports=['kiwipiepy_model'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='main',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
