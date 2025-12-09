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
        st.error("❌ **Missing Dependencies!**")
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

# Custom CSS for attractive styling
st.markdown("""
<style>
    /* Main container */
    .main .block-container {
        padding-top: 2rem;
    }
    
    /* Title styling with gradient background */
    h1 {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        font-size: 3rem;
        font-weight: 800;
        margin-bottom: 0.5rem;
        text-align: center;
    }
    
    /* Subtitle styling */
    .subtitle-text {
        color: #667eea;
        font-size: 1.3rem;
        text-align: center;
        margin-bottom: 2.5rem;
        font-weight: 500;
    }
    
    /* Chat message bubbles */
    .stChatMessage {
        padding: 1rem;
        border-radius: 15px;
        margin: 0.5rem 0;
    }
    
    /* User message styling */
    [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] {
        padding: 0.75rem 1rem;
    }
    
    /* Sidebar styling with gradient */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #f0f4ff 0%, #e8f0fe 100%);
    }
    
    /* Sidebar header */
    [data-testid="stSidebar"] h2 {
        color: #667eea;
        font-weight: 700;
    }
    
    /* Button styling with gradient */
    .stButton > button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        border-radius: 12px;
        padding: 0.6rem 1.5rem;
        font-weight: 600;
        font-size: 1rem;
        width: 100%;
        transition: all 0.3s ease;
        box-shadow: 0 4px 6px rgba(102, 126, 234, 0.3);
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 12px rgba(102, 126, 234, 0.4);
        background: linear-gradient(135deg, #764ba2 0%, #667eea 100%);
    }
    
    /* Chat input styling */
    .stChatInput > div > div {
        border-radius: 25px;
        border: 2px solid #667eea;
        background: white;
    }
    
    .stChatInput > div > div:focus-within {
        border-color: #764ba2;
        box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
    }
    
    /* Remove divider styling */
    hr {
        display: none;
    }
    
    /* Success message styling */
    .stSuccess {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border-radius: 10px;
    }
</style>
""", unsafe_allow_html=True)

# Title and description with attractive styling
st.markdown("### 🎓 UCU Student Assistant Chatbot")
st.markdown('<p class="subtitle-text">Ask anything about <strong style="color: #764ba2;">Uganda Christian University</strong>! 👋</p>', unsafe_allow_html=True)

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

# Sidebar with info
with st.sidebar:
    st.header("ℹ️ About")
    st.markdown("""
    This chatbot uses **zero-shot classification** with MiniLM-v2 to answer questions about UCU.
    
    **Try asking:**
    - Who is the vice chancellor?
    - Where is Alan Galpin Health Centre?
    - Library opening hours
    - Campus locations
    """)
    
    st.divider()
    
    if st.button("🔄 Reload Intents"):
        """Reload intents.json if you've made changes"""
        reload_intents()
        st.success("Intents reloaded! Changes from intents.json are now active.")
        st.rerun()
    
    if st.button("🗑️ Clear Chat History"):
        st.session_state.messages = []
        st.rerun()

