import json
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
import torch
from torch.utils.data import Dataset, DataLoader
from torch.optim import AdamW  # FIXED: Import from torch instead of transformers
from transformers import (
    AutoTokenizer, 
    AutoModelForSequenceClassification,
    get_linear_schedule_with_warmup
)
from tqdm import tqdm
import os
from config import config

class IntentDataset(Dataset):
    def __init__(self, texts, labels, tokenizer, max_length):
        self.texts = texts
        self.labels = labels
        self.tokenizer = tokenizer
        self.max_length = max_length
    
    def __len__(self):
        return len(self.texts)
    
    def __getitem__(self, idx):
        text = str(self.texts[idx])
        label = self.labels[idx]
        
        encoding = self.tokenizer(
            text,
            truncation=True,
            padding='max_length',
            max_length=self.max_length,
            return_tensors='pt'
        )
        
        return {
            'input_ids': encoding['input_ids'].flatten(),
            'attention_mask': encoding['attention_mask'].flatten(),
            'labels': torch.tensor(label, dtype=torch.long)
        }

def load_and_prepare_data(json_path):
    """Load JSON data and prepare for training"""
    with open(json_path, 'r') as f:
        data = json.load(f)
    
    texts = []
    labels = []
    tag_to_id = {}
    
    # Extract patterns and labels
    for i, intent in enumerate(data['intents']):
        tag = intent['tag']
        if tag not in tag_to_id:
            tag_to_id[tag] = len(tag_to_id)
        
        for pattern in intent['patterns']:
            texts.append(pattern)
            labels.append(tag_to_id[tag])
    
    # Update number of labels in config
    config.NUM_LABELS = len(tag_to_id)
    
    return texts, labels, tag_to_id

def train_model():
    """Main training function"""
    print("Loading and preparing data...")
    texts, labels, tag_to_id = load_and_prepare_data(config.DATA_PATH)
    
    # Save tag mapping
    with open('tag_mapping.json', 'w') as f:
        json.dump(tag_to_id, f, indent=2)
    
    print(f"Loaded {len(texts)} training examples")
    print(f"Number of classes: {config.NUM_LABELS}")
    print(f"Classes: {list(tag_to_id.keys())}")
    
    # Split data
    train_texts, val_texts, train_labels, val_labels = train_test_split(
        texts, labels, test_size=0.2, random_state=42, stratify=labels
    )
    
    print(f"Training samples: {len(train_texts)}")
    print(f"Validation samples: {len(val_texts)}")
    
    # Initialize tokenizer and model
    tokenizer = AutoTokenizer.from_pretrained(config.MODEL_NAME)
    model = AutoModelForSequenceClassification.from_pretrained(
        config.MODEL_NAME, 
        num_labels=config.NUM_LABELS
    )
    model.to(config.DEVICE)
    
    # Create datasets
    train_dataset = IntentDataset(train_texts, train_labels, tokenizer, config.MAX_LENGTH)
    val_dataset = IntentDataset(val_texts, val_labels, tokenizer, config.MAX_LENGTH)
    
    # Create data loaders
    train_loader = DataLoader(train_dataset, batch_size=config.BATCH_SIZE, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=config.BATCH_SIZE)
    
    # Optimizer and scheduler - FIXED: Using torch.optim.AdamW
    optimizer = AdamW(model.parameters(), lr=config.LEARNING_RATE)
    total_steps = len(train_loader) * config.EPOCHS
    scheduler = get_linear_schedule_with_warmup(
        optimizer,
        num_warmup_steps=0,
        num_training_steps=total_steps
    )
    
    # Training loop
    best_accuracy = 0
    training_losses = []
    
    print("Starting training...")
    for epoch in range(config.EPOCHS):
        model.train()
        total_loss = 0
        
        progress_bar = tqdm(train_loader, desc=f'Epoch {epoch+1}/{config.EPOCHS}')
        
        for batch in progress_bar:
            input_ids = batch['input_ids'].to(config.DEVICE)
            attention_mask = batch['attention_mask'].to(config.DEVICE)
            labels = batch['labels'].to(config.DEVICE)
            
            optimizer.zero_grad()
            
            outputs = model(
                input_ids=input_ids,
                attention_mask=attention_mask,
                labels=labels
            )
            
            loss = outputs.loss
            total_loss += loss.item()
            
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            
            progress_bar.set_postfix({'loss': loss.item()})
        
        avg_loss = total_loss / len(train_loader)
        training_losses.append(avg_loss)
        
        # Validation
        model.eval()
        val_accuracy = 0
        val_samples = 0
        
        with torch.no_grad():
            for batch in val_loader:
                input_ids = batch['input_ids'].to(config.DEVICE)
                attention_mask = batch['attention_mask'].to(config.DEVICE)
                labels = batch['labels'].to(config.DEVICE)
                
                outputs = model(
                    input_ids=input_ids,
                    attention_mask=attention_mask
                )
                
                predictions = torch.argmax(outputs.logits, dim=1)
                val_accuracy += (predictions == labels).sum().item()
                val_samples += labels.size(0)
        
        accuracy = val_accuracy / val_samples
        print(f'Epoch {epoch+1}: Loss = {avg_loss:.4f}, Validation Accuracy = {accuracy:.4f}')
        
        # Save best model
        if accuracy > best_accuracy:
            best_accuracy = accuracy
            model.save_pretrained(config.SAVE_PATH)
            tokenizer.save_pretrained(config.SAVE_PATH)
            print(f"New best model saved with accuracy: {best_accuracy:.4f}")
    
    print(f"Training completed! Best validation accuracy: {best_accuracy:.4f}")
    return model, tokenizer, tag_to_id

if __name__ == "__main__":
    train_model()