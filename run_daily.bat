@echo off
REM ============================================================
REM  Wisuno Daily Carousel Runner
REM  Scheduled via Windows Task Scheduler at 9:00 AM (Dubai time)
REM ============================================================
cd /d "C:\Users\Eduardo\Desktop\Triache\Marketing\wisuno-carousel"
call .venv\Scripts\activate.bat
python daily_workflow.py >> output\scheduler.log 2>&1
