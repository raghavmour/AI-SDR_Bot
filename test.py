import jwt
from datetime import datetime, timedelta

JWT_SECRET = "your_secret_key"
JWT_ALGORITHM = "HS256"

payload = {
    "email": "user@example.com",
    "exp": datetime.utcnow() + timedelta(hours=1)
}

token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
print(token)
