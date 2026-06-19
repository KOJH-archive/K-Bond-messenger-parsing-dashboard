@echo off
echo.
echo ==========================================
echo   K-Bond OCR Scraper Setup ^& Runner
echo ==========================================
echo.

echo 1. Checking/Installing Dependencies...
echo (Large download of Torch/EasyOCR may take a few minutes...)
py -m pip install easyocr opencv-python pillow requests numpy pyautogui uiautomation

echo.
echo 2. Running K-Bond OCR Scraper...
py kbond_ocr_scraper.py

pause
