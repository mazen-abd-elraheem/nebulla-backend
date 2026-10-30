@echo off
title Nebula AI Robot Backend (GPU Accelerated)
echo ====================================================================
echo Starting Nebula Backend with NVIDIA GeForce GTX 1650 (CUDA)
echo ====================================================================
echo Python Environment: D:\nebula_venv\Scripts\python.exe
echo Swagger UI:         http://localhost:8000/docs
echo Interactive Demo:   http://localhost:8000/demo
echo ====================================================================
echo.
D:\nebula_venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
pause
