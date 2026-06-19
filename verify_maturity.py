import requests
import time

data = {
    "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
    "raw": "[채권] 블커본드 (12:00:00) : 국고24-7 27.09.10 3.25",
    "sender": "[채권] 블커본드",
    "time": "12:00:00",
    "ticker": "24-7",
    "maturity": "27.09.10",
    "side": "거래",
    "content": "국고24-7 27.09.10 3.25"
}

try:
    response = requests.post("http://localhost:5000/update", json=data)
    print(f"Status: {response.status_code}, Response: {response.json()}")
except Exception as e:
    print(f"Error: {e}")
