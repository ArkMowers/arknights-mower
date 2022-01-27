# -*- mode: python ; coding: utf-8 -*-


block_cipher = None


a = Analysis(['main.py'],
             binaries=[],
             datas=[
                ('arknights_mower/fonts', 'arknights_mower/__init__/fonts'),
                ('arknights_mower/models', 'arknights_mower/__init__/models'),
                ('arknights_mower/templates', 'arknights_mower/__init__/templates'),
                ('arknights_mower/resources', 'arknights_mower/__init__/resources'),
                ('venv64/Lib/site-packages/onnxruntime/capi/onnxruntime_providers_shared.dll', 'onnxruntime/capi/'),
             ],
             hiddenimports=[],
             hookspath=[],
             hooksconfig={},
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)

pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)

exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
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
          target_arch=None,
          codesign_identity=None,
          entitlements_file=None )
