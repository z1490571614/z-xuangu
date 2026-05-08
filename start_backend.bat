@echo off
set PYTHONIOENCODING=utf-8
call conda activate xuangu
uvicorn backend.main:app --host 127.0.0.1 --port 9999 --workers 1