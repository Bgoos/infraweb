@echo off
cd C:\Docker\infraweb
call venv\Scripts\activate
python scripts\windows_vm_collection.py
python scripts\test_collection.py
deactivate