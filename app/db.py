from pymongo import MongoClient
import os
from dotenv import load_dotenv
import bcrypt
from datetime import datetime, timedelta
import jwt



load_dotenv()

MONGO_URI = os.getenv("MONGODB_URI")
JWT_SECRET = os.getenv("JWT_SECRET", "your-secret-key")  # Set in .env
JWT_ALGORITHM = "HS256"

try:
    client = MongoClient(MONGO_URI)
    db = client["ai_sdr_db"]
    conversations_collection = db["conversations"]
    users_collection = db["users"]
    tokens_collection = db["tokens"]
except Exception as e:
    print(f"Error connecting to MongoDB: {e}")
    raise

# Save a message to the database
def save_message(user_id: str, sender: str, message: str):
    try:
        conversations_collection.update_one(
            {"user_id": user_id},
            {
                "$push": {
                    "messages": {
                        "sender": sender,
                        "message": message,
                        "timestamp": datetime.utcnow()
                    }
                },
                "$setOnInsert": {
                    "user_id": user_id,
                    "escalated": False
                }
            },
            upsert=True
        )
    except Exception as e:
        print(f"Error saving message: {e}")
        raise

# Get the latest N messages for a user
def get_last_messages(user_id: str, limit: int = 4):
    try:
        conversation = conversations_collection.find_one({"user_id": user_id})
        if conversation and "messages" in conversation:
            # Sort messages by timestamp descending and get the last 'limit' messages
            messages = sorted(conversation["messages"], key=lambda x: x["timestamp"], reverse=True)[:limit]
            # Convert to the same format as before
            formatted_messages = [
                {
                    "_id": str(i),  # Generate a fake _id for compatibility
                    "user_id": user_id,
                    "sender": msg["sender"],
                    "message": msg["message"]
                }
                for i, msg in enumerate(messages)
            ]
            return formatted_messages[::-1]  # Reverse to maintain chronological order
        return []
    except Exception as e:
        print(f"Error retrieving messages: {e}")
        return []

# Get all messages for a user
def get_all_messages(user_id: str):
    try:
        conversation = conversations_collection.find_one({"user_id": user_id})
        if conversation and "messages" in conversation:
            # Sort messages by timestamp ascending
            messages = sorted(conversation["messages"], key=lambda x: x["timestamp"])
            # Convert to the same format as before
            formatted_messages = [
                {
                    "_id": str(i),  # Generate a fake _id for compatibility
                    "user_id": user_id,
                    "sender": msg["sender"],
                    "message": msg["message"]
                }
                for i, msg in enumerate(messages)
            ]
            return formatted_messages
        return []
    except Exception as e:
        print(f"Error retrieving messages: {e}")
        return []

# Set escalation status for a user's conversation
def set_escalation_status(user_id: str, escalated: bool):
    try:
        result = conversations_collection.update_one(
            {"user_id": user_id},
            {"$set": {"escalated": escalated}}
        )
        if result.matched_count > 0:
            return True, "Escalation status updated successfully"
        return False, "No conversation found for user"
    except Exception as e:
        print(f"Error updating escalation status: {e}")
        return False, str(e)

# Get escalation status for a user's conversation
def get_escalation_status(user_id: str):
    try:
        conversation = conversations_collection.find_one({"user_id": user_id})
        if conversation:
            return True, conversation.get("escalated", False)
        return False, "No conversation found for user"
    except Exception as e:
        print(f"Error retrieving escalation status: {e}")
        return False, str(e)

# Create a new user
def create_user(email: str, password: str):
    try:
        if users_collection.find_one({"email": email}):
            return False, "User already exists"
        hashed_password = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
        users_collection.insert_one({
            "email": email,
            "password": hashed_password
        })
        return True, "User created successfully"
    except Exception as e:
        print(f"Error creating user: {e}")
        return False, str(e)

# Authenticate a user and generate tokens


def authenticate_user(email: str, password: str):
    try:
        user = users_collection.find_one({"email": email})
        if user and bcrypt.checkpw(password.encode("utf-8"), user["password"]):
            # Generate access token (1-hour expiry)
            access_token = jwt.encode({
                "email": email,
                "exp": datetime.utcnow() + timedelta(hours=1)
            }, JWT_SECRET, algorithm=JWT_ALGORITHM)
            # Generate refresh token (7-day expiry)
            refresh_token = jwt.encode({
                "email": email,
                "exp": datetime.utcnow() + timedelta(days=7)
            }, JWT_SECRET, algorithm=JWT_ALGORITHM)
            # Store refresh token
            tokens_collection.update_one(
                {"email": email},
                {"$set": {"refresh_token": refresh_token, "created_at": datetime.utcnow()}},
                upsert=True
            )
            return True, {"access_token": access_token, "refresh_token": refresh_token, "email": email}
        return False, "Invalid email or password"
    except Exception as e:
        print(f"Error authenticating user: {e}")
        return False, str(e)
# Validate JWT token
def validate_token(token: str):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return True, payload["email"]
    except jwt.ExpiredSignatureError:
        return False, "Token expired"
    except jwt.InvalidTokenError:
        return False, "Invalid token"

# Refresh access token
def refresh_access_token(refresh_token: str):
    try:
        # Validate refresh token
        payload = jwt.decode(refresh_token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        email = payload["email"]
        # Check if refresh token exists in DB
        token_doc = tokens_collection.find_one({"email": email, "refresh_token": refresh_token})
        if not token_doc:
            return False, "Invalid refresh token"
        # Generate new access token
        new_access_token = jwt.encode({
            "email": email,
            "exp": datetime.utcnow() + timedelta(hours=1)
        }, JWT_SECRET, algorithm=JWT_ALGORITHM)
        return True, {"access_token": new_access_token, "email": email}
    except jwt.ExpiredSignatureError:
        return False, "Refresh token expired"
    except jwt.InvalidTokenError:
        return False, "Invalid refresh token"

# Revoke refresh token (logout)
def revoke_refresh_token(email: str):
    try:
        tokens_collection.delete_one({"email": email})
        return True, "Logged out successfully"
    except Exception as e:
        print(f"Error revoking token: {e}")
        return False, str(e)