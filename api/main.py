from dotenv import load_dotenv
import os
from fastapi import FastAPI

app = FastAPI()
load_dotenv()
openai_api_key = os.getenv("OPENAI_API_KEY")




from fastapi import FastAPI, Request
from pydantic import BaseModel
from app.chatbot import chat_with_lead

app = FastAPI()

class LeadMessage(BaseModel):
    message: str

@app.post("/chat")
def chat(message: LeadMessage):
    reply = chat_with_lead(message.message)
    return {"reply": reply}