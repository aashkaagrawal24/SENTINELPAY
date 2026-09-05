@echo off
echo Starting SentinelPay Backend (FastAPI on http://127.0.0.1:8001)...
start "SentinelPay Backend" cmd /k "cd /d c:\Users\sawan\OneDrive\Desktop\RAZORPAY\backend && .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload"

echo Starting SentinelPay Frontend (Next.js on http://localhost:3001)...
start "SentinelPay Frontend" cmd /k "cd /d c:\Users\sawan\OneDrive\Desktop\RAZORPAY\frontend\web && npm run dev"

echo Both servers started in separate terminal windows!
