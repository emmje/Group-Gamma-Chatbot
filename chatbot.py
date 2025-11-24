
import json
import random
from intent_classifier import UCUIntentClassifier

class UCUChatbot:
    def __init__(self, model_path=None):
        self.classifier = UCUIntentClassifier(model_path)
        self.load_responses()
        
    def load_responses(self):
        """Load responses from the intents.json file"""
        with open('intents.json', 'r') as f:
            data = json.load(f)
        
        self.responses = {}
        for intent in data['intents']:
            self.responses[intent['tag']] = intent['responses']
    
    def get_response(self, intent):
        """Get a random response for the given intent"""
        if intent in self.responses:
            return random.choice(self.responses[intent])
        else:
            return "I'm not sure how to respond to that. Can you try asking differently?"
    
    def chat(self):
        """Start an interactive chat session"""
        print("🤖 UCU Chatbot: Hello! I'm your UCU assistant. How can I help you today?")
        print("Type 'quit', 'exit', or 'bye' to end the conversation.\n")
        
        while True:
            try:
                user_input = input("You: ").strip()
                
                if not user_input:
                    continue
                
                # Check for exit commands
                if user_input.lower() in ['quit', 'exit', 'bye', 'goodbye']:
                    print("🤖 UCU Chatbot: Goodbye! God bless you. Come back anytime you need help.")
                    break
                
                # Predict intent and get response
                intent, confidence = self.classifier.predict(user_input, return_confidence=True)
                response = self.get_response(intent)
                
                print(f"🤖 UCU Chatbot: {response}")
                print(f"   [Intent: {intent}, Confidence: {confidence:.3f}]\n")
                
            except KeyboardInterrupt:
                print("\n🤖 UCU Chatbot: Goodbye! Have a blessed day!")
                break
            except Exception as e:
                print(f"🤖 UCU Chatbot: I encountered an error. Please try again.")
                print(f"   [Error: {e}]\n")

if __name__ == "__main__":
    chatbot = UCUChatbot()
    chatbot.chat()