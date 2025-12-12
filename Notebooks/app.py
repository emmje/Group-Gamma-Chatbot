# app.py - Streamlit Interface for UCU Chatbot
import streamlit as st
import sys
import subprocess

# Check and install dependencies if missing
def check_dependencies():
    """Check if required packages are installed, show error if not"""
    try:
        from chatbot_zeroshot import get_response, reload_intents
        return get_response, reload_intents
    except ImportError as e:
        st.error("**Missing Dependencies!**")
        st.markdown("""
        ### Required packages are not installed.
        
        **To fix this, run in your terminal:**
        ```bash
        pip install -r requirements_zeroshot.txt
        ```
        
        Or install individually:
        ```bash
        pip install sentence-transformers streamlit
        ```
        
        Then refresh this page.
        """)
        st.stop()
        return None, None

# Check dependencies before proceeding
get_response, reload_intents = check_dependencies()

# Page configuration
st.set_page_config(
    page_title="UCU Chatbot",
    page_icon="🎓",
    layout="centered",
    initial_sidebar_state="expanded"
)

# Custom CSS for clean, simple styling
st.markdown("""
<style>
    /* Main container */
    .main .block-container {
        padding-top: 2rem;
    }
    
    /* Title styling - simple and clean */
    h1 {
        color: #1f2937;
        font-size: 2.5rem;
        font-weight: 700;
        margin-bottom: 0.5rem;
        text-align: center;
    }
    
    /* Subtitle styling */
    .subtitle-text {
        color: #4b5563;
        font-size: 1.2rem;
        text-align: center;
        margin-bottom: 2rem;
    }
    
    /* Sidebar header */
    [data-testid="stSidebar"] h2 {
        color: #1f2937;
        font-weight: 600;
    }
    
    /* Button styling - simple solid color */
    .stButton > button {
        background-color: #3b82f6;
        color: white;
        border: none;
        border-radius: 8px;
        padding: 0.5rem 1rem;
        font-weight: 500;
        width: 100%;
    }
    
    .stButton > button:hover {
        background-color: #2563eb;
    }
    
    /* Remove divider styling */
    hr {
        display: none;
    }
</style>
""", unsafe_allow_html=True)

# Title and description - clean and simple
st.markdown("### 🎓 UCU Student Assistant Chatbot")
st.markdown('<p class="subtitle-text">Ask anything about <strong>Uganda Christian University</strong>!</p>', unsafe_allow_html=True)

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Chat input
if prompt := st.chat_input("Type your message here..."):
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Get bot response
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            response = get_response(prompt)
        st.markdown(response)
    
    # Add assistant response to chat history
    st.session_state.messages.append({"role": "assistant", "content": response})

# Sidebar with chat history
with st.sidebar:
    st.header("💬 Chat History")
    
    # Show chat history (only user questions)
    if st.session_state.messages:
        user_questions = [msg["content"] for msg in st.session_state.messages if msg["role"] == "user"]
        
        if user_questions:
            st.markdown("**Previous Questions:**")
            for i, question in enumerate(user_questions[-10:], 1):  # Show last 10 questions
                st.markdown(f"{i}. {question}")
        else:
            st.info("No questions yet. Start chatting!")
    else:
        st.info("No chat history yet. Start asking questions!")
    
    st.divider()
    
    if st.button("🔄 Reload Intents"):
        """Reload intents.json if you've made changes"""
        reload_intents()
        st.success("Intents reloaded! Changes from intents.json are now active.")
        st.rerun()
    
    if st.button("🗑️ Clear Chat History"):
        st.session_state.messages = []
        st.rerun()

