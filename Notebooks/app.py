# app.py - Streamlit Interface for UCU Chatbot
import streamlit as st
from chatbot_zeroshot import get_response, reload_intents

# Page configuration
st.set_page_config(
    page_title="UCU Chatbot",
    page_icon="🎓",
    layout="centered"
)

# Title and description
st.title("🎓 UCU Student Assistant Chatbot")
st.markdown("Ask anything about **Uganda Christian University**!")
st.divider()

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
    
    st.divider()
    st.caption("💡 **Tip:** After editing intents.json, click 'Reload Intents' to update the chatbot without restarting.")

