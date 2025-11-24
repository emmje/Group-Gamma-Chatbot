import os
import torch

class Config:
    # Model
    MODEL_NAME = "distilbert-base-uncased"
    NUM_LABELS = 14  # This will be updated automatically
    
    # Training
    BATCH_SIZE = 16
    LEARNING_RATE = 2e-5
    EPOCHS = 10
    MAX_LENGTH = 128
    
    # Data - UPDATED: Use local file in same directory
    DATA_PATH = "intents.json"
    
    # Device
    DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    
    # Save paths - UPDATED: Save locally
    SAVE_PATH = "ucu_intent_model"
    
config = Config()