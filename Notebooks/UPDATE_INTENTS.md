# How to Update intents.json

## Quick Answer

**After editing `intents.json`, you need to reload the chatbot:**

### For Terminal Chatbot:
1. Stop the chatbot (press `Ctrl+C`)
2. Run it again: `python3 chatbot_zeroshot.py`

### For Streamlit Web Interface:
1. Click the **"🔄 Reload Intents"** button in the sidebar, OR
2. Stop Streamlit (press `Ctrl+C`) and restart: `streamlit run app.py`

## What You Can Change

You can modify `intents.json` to:
- ✅ Add new intents (new tags)
- ✅ Add new patterns to existing intents
- ✅ Add new responses to existing intents
- ✅ Modify existing responses
- ✅ Remove intents

## Example: Adding a New Intent

```json
{
  "tag": "new_intent",
  "patterns": [
    "What is the cafeteria menu",
    "What food is available",
    "What's for lunch"
  ],
  "responses": [
    "The cafeteria serves a variety of meals including local and international dishes.",
    "Check the daily menu posted at the dining hall entrance."
  ]
}
```

After adding this, reload the chatbot and it will work immediately!

## Example: Adding to Existing Intent

Find an existing intent in `intents.json` and add to it:

```json
{
  "tag": "greetings",
  "patterns": [
    "Hello",
    "Hi",
    "Hey",
    "Good morning",
    "What's up"  // ← Add new pattern here
  ],
  "responses": [
    "Hello! How can I assist you today?",
    "Hi there! What do you need help with?",
    "Welcome! How can I help?"  // ← Add new response here
  ]
}
```

## No Training Required! 🎉

Unlike traditional chatbots, **zero-shot classification doesn't require retraining**. Just:
1. Edit `intents.json`
2. Reload the chatbot
3. Done!

The model automatically understands the new patterns using semantic similarity.


