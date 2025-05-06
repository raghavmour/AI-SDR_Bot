import os
from dotenv import load_dotenv
from langchain_openai.chat_models import ChatOpenAI
from langchain.schema import HumanMessage, AIMessage
from app.prompts import base_prompt
from app.retriever import retrieve_relevant_chunks
from app.db import save_message, get_last_messages, get_all_messages, set_escalation_status, get_escalation_status
import streamlit as st
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import tiktoken  # Added for token counting
from app.prompts import stage_analyzer_prompt

load_dotenv()

# Initialize tokenizer for gpt-3.5-turbo (uses cl100k_base encoding)
tokenizer = tiktoken.get_encoding("cl100k_base")


# llm = ChatOpenAI(
#    openai_api_key=os.getenv("GROQ_API_KEY"),
#    temperature=0.0,
#    model_name= "llama3-70b-8192",   #"mistral-saba-24b",
#    base_url="https://api.groq.com/openai/v1"  # Groq uses OpenAI-compatible API
# )
llm = ChatOpenAI(
    openai_api_key=os.getenv("OPENROUTER_API_KEY"),
    temperature=0.0,
    model_name="gpt-3.5-turbo",
    base_url="https://openrouter.ai/api/v1"
)

# Email configuration
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))

def send_escalation_email(user_id: str, intent: str, history: list, stage: int):
    try:
        # Generate summary and score
        summary = generate_lead_summary(history, stage, intent)
        score = calculate_lead_score(stage, intent)

        # Prepare email content
        msg = MIMEMultipart()
        msg["From"] = EMAIL_SENDER
        msg["To"] = user_id  # User_id is the user's email
        msg["Subject"] = "Your Request for Human Assistance"

        # Email body with summary and score
        reason_text = (
            "you expressed strong interest in our product" if intent == "interest"
            else "you seemed to need more personalized assistance"
        )
        body = f"""
        Dear valued user,

        Thank you for interacting with our AI SDR Assistant! We've flagged your conversation for a human agent because {reason_text}. A member of our team will reach out to you within the next 24 hours to assist you further.

        🧠 Lead Summary:
        {summary}

        📊 Lead Score: {score}/100

        If you have any urgent questions, feel free to contact us at support@example.com.

        Best regards,  
        The AI SDR Team
        """
        msg.attach(MIMEText(body, "plain"))

        # Connect to SMTP server
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, user_id, msg.as_string())
        print(f"Escalation email sent to {user_id}")
        return True, "Email sent successfully"
    except Exception as e:
        print(f"Error sending escalation email to {user_id}: {e}")
        return False, str(e)

def analyze_stage(user_message: str, history_f: list) -> int:
    try:
        # Format conversation history
        formatted_history = "\n".join(
            [f"{'User' if isinstance(m, HumanMessage) else 'AI'}: {m.content}" for m in history_f]
        )
        stage_input_prompt = stage_analyzer_prompt.format(
            history=formatted_history, message=user_message
        )
        input_message = HumanMessage(content=stage_input_prompt)
        response = llm.invoke([input_message])
        stage_str = response.content.strip()

        stage = int(stage_str)
        print(f"Detected stage: {stage}")
        return stage
    except Exception as e:
        print(f"Error analyzing stage: {e}")
        return 1  # Default to Introduction


# Fetch session history from MongoDB
def get_session_history(user_id: str):
    try:
        messages = get_last_messages(user_id=user_id, limit=4)
        history = []
        for msg in messages:
            if msg["sender"] == "user":
                history.append(HumanMessage(content=msg["message"]))
            else:
                history.append(AIMessage(content=msg["message"]))
        return history
    except Exception as e:
        print(f"Error fetching session history: {e}")
        return []

def get_full_session_history(user_id: str):
    try:
        messages_f = get_all_messages(user_id=user_id)
        history_f = []
        for msg in messages_f:
            if msg["sender"] == "user":
                history_f.append(HumanMessage(content=msg["message"]))
            else:
                history_f.append(AIMessage(content=msg["message"]))
        return history_f
    except Exception as e:
        print(f"Error fetching session history: {e}")
        return []

def detect_intent(user_message: str, history: list) -> str:
    intent_prompt = f"""
Based on the following user message and conversation history, classify the user's intent as one of:
- 'interest' (e.g., asking about product details, features, demos, or showing enthusiasm with positive tone like 'excited,' 'great')
- 'frustration' (e.g., complaints, repeated questions, negative tone like 'annoying,' 'not working,' or use of '?!')
- 'neutral' (e.g., general inquiries with no strong sentiment, like factual questions about features or processes)

User message: {user_message}
Conversation history (chronological, user and bot messages): {history}

Rules:
- Analyze tone (e.g., positive/negative adjectives, punctuation like '!' or '?!') and keywords (e.g., 'help,' 'issue' for frustration; 'interested,' 'cool' for interest).
- If mixed intents are detected, prioritize 'frustration' for escalation.
- Use conversation history to detect context, prioritizing recent messages. Classify as 'frustration' if the user repeats a question or expresses dissatisfaction without resolution.
- For escalation, treat multiple unresolved neutral inquiries as 'frustration.'

Provide the intent as a single word: interest, frustration, or neutral
"""
    intent_input = [HumanMessage(content=intent_prompt)]
    response = llm.invoke(intent_input)
    
    # Count input and output tokens for intent detection
    input_text = intent_prompt
    output_text = response.content.strip()
    input_tokens = len(tokenizer.encode(input_text))
    output_tokens = len(tokenizer.encode(output_text))
    print(f"Intent Detection - Input Tokens: {input_tokens}, Output Tokens: {output_tokens}")
    
    return output_text.lower()

def calculate_lead_score(stage: int, intent: str) -> int:
    base = stage * 10
    if intent == "interest":
        return min(base + 30, 100)
    elif intent == "frustration":
        return max(base - 10, 0)
    return base

def generate_lead_summary(history: list, stage: int, intent: str) -> str:
    try:
        conversation = "\n".join([f"{'User' if isinstance(m, HumanMessage) else 'AI'}: {m.content}" for m in history])
        prompt = f"""
Given this conversation between a sales AI and a user, summarize the lead in 2-3 sentences. Include:
- Role or company (if mentioned)
- Key pain points or questions
- Detected stage: {stage}
- Detected intent: {intent}

Conversation:
{conversation}

Lead Summary:
"""
        response = llm.invoke([HumanMessage(content=prompt)])
        return response.content.strip()
    except Exception as e:
        print(f"Error generating summary: {e}")
        return "Summary unavailable."


# Chat function with token counting
def chat_with_lead(user_id: str, user_message: str) -> str:
    try:
        context = retrieve_relevant_chunks(user_message)
        history = get_full_session_history(user_id)
        history_f = get_full_session_history(user_id)
        stage = analyze_stage(user_message, history_f)
        formatted_prompt = base_prompt.format(stage = stage,history=history, input=user_message) + f"\n\nRelevant Company Info:\n{context}"
        human_message = HumanMessage(content=formatted_prompt)

        intent = detect_intent(user_message, history_f)
        

        #print("stage\n" ,stage)
        # Count input tokens for chat response
        input_text = formatted_prompt
        input_tokens = len(tokenizer.encode(input_text))
        
        response = llm.invoke([human_message])
        ai_reply = response.content
        
        # Count output tokens for chat response
        output_tokens = len(tokenizer.encode(ai_reply))
        
        # Print token counts
        print(f"Chat Response - Input Tokens: {input_tokens}, Output Tokens: {output_tokens}")
        print("Prompt:", formatted_prompt)
        print("Intent:", intent)

        # Save messages
        save_message(user_id, "user", user_message)
        save_message(user_id, "ai", ai_reply)

        # Check escalation status and conversation length
        success, escalated = get_escalation_status(user_id)
        if success and not escalated:  # Only escalate if not already escalated
            # Check if conversation has at least 6 messages (3 user + 3 AI)
            all_messages = get_all_messages(user_id)
            if len(all_messages) >= 6:  # Assuming alternating user/AI messages
                  if stage >= 6 and intent in ["interest", "frustration"]:
                    success, message = set_escalation_status(user_id, True)
                    if success:
                        # Send email notification to user
                        email_success, email_message = send_escalation_email(user_id, intent, history, stage)
                        if not email_success:
                            print(f"Warning: {email_message}")
                        reason = (
                            "you seem really interested in our product" if intent == "interest"
                            else "it seems like you might need more personalized assistance"
                        )
                        return ai_reply + f" 🚀 I've flagged this for a human agent because {reason}. They'll reach out shortly."
                    else:
                        print(f"Failed to set escalation status: {message}")

        return ai_reply
    except Exception as e:
        print(f"Error in chat_with_lead: {e}")
        return "Sorry, something went wrong. Please try again."