@echo off
mklink /J "D:\devEco\DevEco Studio\sdk\default\24" "D:\devEco\DevEco Studio\sdk\default\openharmony"
if %errorlevel% equ 0 (echo SUCCESS) else (echo FAILED -可能需要管理员权限)
