import requests
res = requests.post("http://localhost:8000/api/auth/login", json={"email": "test@best.com", "password": "password_123"})
print(res.status_code)
print(res.json())
