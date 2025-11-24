import torch
import json
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from config import config

class UCUIntentClassifier:
    def __init__(self, model_path=None):
        if model_path is None:
            model_path = config.SAVE_PATH
        
        self.device = config.DEVICE
        self.tokenizer = AutoTokenizer.from_pretrained(model_path)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_path)
        self.model.to(self.device)
        self.model.eval()
        
        # Load tag mapping
        with open('tag_mapping.json', 'r') as f:
            self.tag_to_id = json.load(f)
        
        self.id_to_tag = {v: k for k, v in self.tag_to_id.items()}
    
    def predict(self, text, return_confidence=False):
        """Predict intent for given text"""
        encoding = self.tokenizer(
            text,
            truncation=True,
            padding='max_length',
            max_length=config.MAX_LENGTH,
            return_tensors='pt'
        )
        
        input_ids = encoding['input_ids'].to(self.device)
        attention_mask = encoding['attention_mask'].to(self.device)
        
        with torch.no_grad():
            outputs = self.model(input_ids=input_ids, attention_mask=attention_mask)
            probabilities = torch.softmax(outputs.logits, dim=1)
            confidence, predicted_class = torch.max(probabilities, dim=1)
        
        intent = self.id_to_tag[predicted_class.item()]
        confidence_score = confidence.item()
        
        if return_confidence:
            return intent, confidence_score
        return intent
    
    def predict_with_all_probabilities(self, text):
        """Predict intent with probabilities for all classes"""
        encoding = self.tokenizer(
            text,
            truncation=True,
            padding='max_length',
            max_length=config.MAX_LENGTH,
            return_tensors='pt'
        )
        
        input_ids = encoding['input_ids'].to(self.device)
        attention_mask = encoding['attention_mask'].to(self.device)
        
        with torch.no_grad():
            outputs = self.model(input_ids=input_ids, attention_mask=attention_mask)
            probabilities = torch.softmax(outputs.logits, dim=1)
        
        results = {}
        for i, prob in enumerate(probabilities[0]):
            intent_name = self.id_to_tag[i]
            results[intent_name] = prob.item()
        
        # Sort by probability
        sorted_results = dict(sorted(results.items(), key=lambda x: x[1], reverse=True))
        return sorted_results

def test_classifier():
    """Test the trained classifier"""
    classifier = UCUIntentClassifier()
    
    test_queries = [
        "Hello there!",
        "Where is the library?",
        "What are the library hours?",
        "Who is the vice chancellor?",
        "How do I apply for admission?",
        "When are the exams?",
        "Goodbye!",
        "What sports facilities are available?"
    ]
    
    print("Testing UCU Intent Classifier:")
    print("-" * 50)
    
    for query in test_queries:
        intent, confidence = classifier.predict(query, return_confidence=True)
        print(f"Query: '{query}'")
        print(f"Intent: {intent} (Confidence: {confidence:.4f})")
        print("-" * 30)

if __name__ == "__main__":
    test_classifier()