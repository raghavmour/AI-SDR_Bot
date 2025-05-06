import streamlit as st
import pandas as pd
from app.chatbot import chat_with_lead, get_session_history, get_full_session_history
from app.vector_db import VectorDB
from app.db import create_user, authenticate_user, validate_token, refresh_access_token, revoke_refresh_token, conversations_collection, get_escalation_status
from langchain.schema import HumanMessage, AIMessage
from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()
MONGO_URI = os.getenv("MONGODB_URI")
client = MongoClient(MONGO_URI)


st.set_page_config(page_title="AI SDR Assistant", page_icon="🤖")

# Custom CSS with enhanced styling
st.markdown("""
    <style>
    .chat-container {
        background-color: #f5f5f5;
        border-radius: 10px;
        padding: 25px;
        height: 60vh;
        max-height: 500px;
        overflow-y: auto;
        margin-bottom: 30px;
    }
    .user-message {
        background-color: #005bbb;
        color: white;
        border-radius: 15px;
        padding: 10px 15px;
        margin: 5px 10px;
        max-width: 70%;
        align-self: flex-end;
        margin-left: auto;
        transition: background-color 0.3s;
    }
    .ai-message {
        background-color: #ffffff;
        color: black;
        border-radius: 15px;
        padding: 10px 15px;
        margin: 5px 10px;
        max-width: 70%;
        align-self: flex-start;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        transition: background-color 0.3s;
    }
    .chat-input-container {
        display: flex;
        align-items: center;
        background-color: #ffffff;
        border-radius: 25px;
        padding: 5px;
        border: 1px solid #ddd;
        margin-top: 20px;
    }
    .chat-input {
        border: none;
        outline: none;
        flex-grow: 1;
        padding: 10px;
        border-radius: 25px;
    }
    .send-button {
        background-color: #005bbb;
        color: white;
        border: none;
        border-radius: 50%;
        width: 40px;
        height: 40px;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        tabindex: 0;
    }
    .send-button:hover {
        background-color: #004080;
    }
    .stFileUploader {
        max-height: 150px;
        overflow-y: auto;
        background-color: #1a1a1a;
        border-radius: 5px;
    }
    .stFileUploader > div {
        margin: 0;
        padding: 10px;
    }
    .login-container {
        max-width: 90%;
        margin: 50px auto;
        padding: 30px;
        background-color: #ffffff;
        border-radius: 15px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
        animation: fadeIn 0.5s ease-in;
    }
    .login-container h1 {
        text-align: center;
        color: #005bbb;
        font-size: 24px;
        margin-bottom: 20px;
    }
    .form-input {
        width: 100%;
        padding: 12px;
        margin: 10px 0;
        border: 1px solid #ddd;
        border-radius: 25px;
        font-size: 16px;
        transition: border-color 0.3s, box-shadow 0.3s;
        tabindex: 0;
    }
    .form-input:focus {
        outline: none;
        border-color: #005bbb;
        box-shadow: 0 0 8px rgba(0, 91, 187, 0.2);
    }
    .form-button {
        width: 100%;
        padding: 12px;
        background-color: #005bbb;
        color: white;
        border: none;
        border-radius: 25px;
        font-size: 16px;
        cursor: pointer;
        transition: background-color 0.3s, transform 0.2s;
        tabindex: 0;
    }
    .form-button:hover {
        background-color: #004080;
        transform: translateY(-2px);
    }
    .form-button:active {
        transform: translateY(0);
    }
    .tabs-container {
        margin-bottom: 20px;
    }
    .brand-logo {
        display: block;
        margin: 0 auto 20px;
        max-width: 100px;
    }
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(20px); }
        to { opacity: 1; transform: translateY(0); }
    }
    </style>
""", unsafe_allow_html=True)

# Initialize session state
if "access_token" not in st.session_state:
    st.session_state.access_token = None
if "refresh_token" not in st.session_state:
    st.session_state.refresh_token = None
if "user_id" not in st.session_state:
    st.session_state.user_id = None
if "messages" not in st.session_state:
    st.session_state.messages = []
if "uploaded_files" not in st.session_state:
    st.session_state.uploaded_files = []
if "login_processed" not in st.session_state:
    st.session_state.login_processed = False
if "page" not in st.session_state:
    st.session_state.page = "chat"

# Check query parameters for tokens
query_params = st.query_params
if not st.session_state.login_processed:
    if "access_token" in query_params and "refresh_token" in query_params:
        st.session_state.access_token = query_params["access_token"]
        st.session_state.refresh_token = query_params["refresh_token"]
        success, result = validate_token(st.session_state.access_token)
        if success:
            st.session_state.user_id = result
            st.session_state.login_processed = True
        else:
            if st.session_state.refresh_token:
                success, refresh_result = refresh_access_token(st.session_state.refresh_token)
                if success:
                    st.session_state.access_token = refresh_result["access_token"]
                    st.session_state.user_id = refresh_result["email"]
                    st.query_params["access_token"] = refresh_result["access_token"]
                    st.session_state.login_processed = True
                else:
                    st.query_params.clear()
                    st.session_state.access_token = None
                    st.session_state.refresh_token = None
                    st.session_state.user_id = None

# Login/Signup UI
def show_auth_page():
    st.markdown("""
        <div class="login-container">
            <h1>AI SDR Assistant</h1>
        </div>
    """, unsafe_allow_html=True)

    tab1, tab2 = st.tabs(["Login", "Sign Up"])

    with tab1:
        st.markdown('<div class="login-container">', unsafe_allow_html=True)
        with st.form("login_form"):
            st.text_input("Email", key="login_email", placeholder="Enter your email", help="Your registered email address")
            st.text_input("Password", type="password", key="login_password", placeholder="Enter your password")
            submit = st.form_submit_button("Login")
            if submit:
                email = st.session_state.login_email
                password = st.session_state.login_password
                success, result = authenticate_user(email, password)
                if success:
                    st.session_state.access_token = result["access_token"]
                    st.session_state.refresh_token = result["refresh_token"]
                    st.session_state.user_id = result["email"]
                    st.session_state.login_processed = True
                    st.query_params.update({
                        "access_token": result["access_token"],
                        "refresh_token": result["refresh_token"]
                    })
                    st.success("Logged in successfully!")
                    st.session_state.rerun_pending = True
                else:
                    st.error(result)
        st.markdown('</div>', unsafe_allow_html=True)

    with tab2:
        st.markdown('<div class="login-container">', unsafe_allow_html=True)
        with st.form("signup_form"):
            st.text_input("Email", key="signup_email", placeholder="Enter your email")
            st.text_input("Password", type="password", key="signup_password", placeholder="Choose a password")
            st.text_input("Confirm Password", type="password", key="signup_confirm_password", placeholder="Confirm your password")
            submit = st.form_submit_button("Sign Up")
            if submit:
                email = st.session_state.signup_email
                password = st.session_state.signup_password
                confirm_password = st.session_state.signup_confirm_password
                if password != confirm_password:
                    st.error("Passwords do not match")
                elif not email or not password:
                    st.error("Please fill in all fields")
                else:
                    success, message = create_user(email, password)
                    if success:
                        st.success("Account created! Please log in.")
                    else:
                        st.error(message)
        st.markdown('</div>', unsafe_allow_html=True)

# Handle delayed rerun
if "rerun_pending" in st.session_state and st.session_state.rerun_pending:
    st.session_state.rerun_pending = False
    st.rerun()

# Validate session
def validate_session():
    if st.session_state.access_token:
        success, result = validate_token(st.session_state.access_token)
        if success:
            st.session_state.user_id = result
            return True
        else:
            if st.session_state.refresh_token:
                success, refresh_result = refresh_access_token(st.session_state.refresh_token)
                if success:
                    st.session_state.access_token = refresh_result["access_token"]
                    st.session_state.user_id = refresh_result["email"]
                    st.query_params["access_token"] = refresh_result["access_token"]
                    st.query_params["refresh_token"] = st.session_state.refresh_token
                    return True
                else:
                    st.session_state.access_token = None
                    st.session_state.refresh_token = None
                    st.session_state.user_id = None
                    st.query_params.clear()
                    return False
            return False
    return False

# Page functions
def show_chat_page():
    st.subheader("Chat with AI SDR")
    success, escalated = get_escalation_status(st.session_state.user_id)
    if success and escalated:
        st.info("Your conversation has been escalated to a human agent!", icon="📞")
    
    def load_chat_history():
        try:
            history = get_full_session_history(st.session_state.user_id)
            st.session_state.messages = []
            for msg in history:
                if isinstance(msg, HumanMessage):
                    st.session_state.messages.append({"role": "user", "content": msg.content})
                elif isinstance(msg, AIMessage):
                    st.session_state.messages.append({"role": "ai", "content": msg.content})
        except Exception as e:
            st.error(f"Failed to load chat history: {e}")
            st.session_state.messages = []

    if not st.session_state.messages:
        load_chat_history()

    st.markdown('<div class="chat-container">', unsafe_allow_html=True)
    for msg in st.session_state.messages:
        if msg["role"] == "user":
            st.markdown(
                f'<div class="user-message" role="log" aria-label="User message">{msg["content"]}</div>',
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                f'<div class="ai-message" role="log" aria-label="AI message">{msg["content"]}</div>',
                unsafe_allow_html=True
            )
    st.markdown('</div>', unsafe_allow_html=True)

    with st.form(key="chat_form", clear_on_submit=True):
        cols = st.columns([4, 1])
        with cols[0]:
            user_input = st.text_input(
                "Type your message...",
                key="user_input",
                label_visibility="collapsed",
                placeholder="Type your message..."
            )
        with cols[1]:
            submit = st.form_submit_button("➤", use_container_width=True)
    
    if submit and user_input:
        st.session_state.messages.append({"role": "user", "content": user_input})
        st.success("Message sent!", icon="✅")
        placeholder = st.empty()
        placeholder.markdown("**AI is typing...**")
        with st.spinner("AI SDR is thinking..."):
            response = chat_with_lead(st.session_state.user_id, user_input)
        placeholder.empty()
        st.session_state.messages.append({"role": "ai", "content": response})
        if st.session_state.access_token and st.session_state.refresh_token:
            st.query_params["access_token"] = st.session_state.access_token
            st.query_params["refresh_token"] = st.session_state.refresh_token
        st.rerun()

def show_upload_page():
    st.subheader("Upload Leads")
    
    def reset_vector_db():
        if "vector_db" in st.session_state:
            st.session_state.vector_db.clear_collection()
            del st.session_state.vector_db
        try:
            st.session_state.vector_db = VectorDB()
        except Exception as e:
            st.error(f"Error initializing vector DB: {e}")
            st.session_state.vector_db = None
    
    if "vector_db" not in st.session_state:
        reset_vector_db()

    uploaded_files = st.file_uploader(
        "📂 Upload files with leads (CSV, TXT, or PDF)",
        type=["csv", "txt", "pdf"],
        accept_multiple_files=True
    )

    if uploaded_files:
        for uploaded_file in uploaded_files:
            file_type = uploaded_file.name.split(".")[-1].lower()
            try:
                if file_type == "csv":
                    df = pd.read_csv(uploaded_file)
                    st.session_state.vector_db.create_vector_db_from_csv(df)
                    st.session_state.uploaded_files.append(uploaded_file.name)
                    st.success(f"📊 CSV '{uploaded_file.name}' uploaded and saved to vector DB!")
                elif file_type == "txt":
                    text = st.session_state.vector_db.extract_text_from_txt(uploaded_file)
                    if text:
                        st.session_state.vector_db.create_vector_db_from_text(text, source_name=f"txt_{uploaded_file.name}")
                        st.session_state.uploaded_files.append(uploaded_file.name)
                        st.success(f"📝 TXT '{uploaded_file.name}' uploaded and saved to vector DB!")
                    else:
                        st.error(f"❌ Failed to process TXT '{uploaded_file.name}'.")
                elif file_type == "pdf":
                    text = st.session_state.vector_db.extract_text_from_pdf(uploaded_file)
                    if text:
                        st.session_state.vector_db.create_vector_db_from_text(text, source_name=f"pdf_{uploaded_file.name}")
                        st.session_state.uploaded_files.append(uploaded_file.name)
                        st.success(f"📄 PDF '{uploaded_file.name}' uploaded and saved to vector DB!")
                    else:
                        st.error(f"❌ Failed to process PDF '{uploaded_file.name}'.")
            except Exception as e:
                st.error(f"❌ Error processing '{uploaded_file.name}': {e}")
    
    if st.session_state.uploaded_files:
        st.write("**Uploaded Files**")
        file_data = [{"File Name": fname} for fname in st.session_state.uploaded_files]
        st.table(file_data)
        if st.button("Clear Uploaded Files"):
            st.session_state.uploaded_files = []
            reset_vector_db()
            st.success("Uploaded files cleared!")
            st.rerun()


# Main app UI
def show_main_app():
    with st.sidebar:
        #st.image("logo.png", width=100, alt="AI SDR Assistant logo")
        st.header("AI SDR Assistant")
        if st.button("Chat", key="nav_chat"):
            st.session_state.page = "chat"
        if st.button("Upload Files", key="nav_upload"):
            st.session_state.page = "upload"
        
        with st.expander("Manage Data"):
            if st.button("🗑️ Clear Vector DB"):
                if "vector_db" in st.session_state:
                    st.session_state.vector_db.clear_collection()
                    del st.session_state.vector_db
                st.session_state.uploaded_files = []
                st.success("Vector DB cleared!")
                st.rerun()
            if st.button("🗑️ Clear Chat History"):
                st.session_state.messages = []
                conversations_collection.delete_many({"user_id": st.session_state.user_id})
                st.success("Chat history cleared!")
                st.rerun()
        if st.button("Logout"):
            success, message = revoke_refresh_token(st.session_state.user_id)
            if success:
                st.session_state.clear()
                st.query_params.clear()
                st.rerun()
            else:
                st.error(message)
    
    if st.session_state.page == "chat":
        show_chat_page()
    elif st.session_state.page == "upload":
        show_upload_page()
    

# Render appropriate page
if validate_session():
    show_main_app()
else:
    show_auth_page()