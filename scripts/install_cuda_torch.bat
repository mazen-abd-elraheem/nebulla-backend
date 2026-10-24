@echo off
set TEMP=D:\pip_temp
set TMP=D:\pip_temp
if not exist D:\pip_temp mkdir D:\pip_temp
if not exist D:\pip_cache mkdir D:\pip_cache
echo [INFO] Redirected TEMP to: %TEMP%
echo [INFO] Redirected TMP to: %TMP%
echo [INFO] Starting PyTorch CUDA installation into D:\nebula_venv ...
D:\nebula_venv\Scripts\pip.exe install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118 --cache-dir D:\pip_cache --no-warn-script-location
echo [INFO] Installation finished with exit code %ERRORLEVEL%
