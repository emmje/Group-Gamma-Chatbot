UCU Chatbot – Zero-Shot Classification with Streamlit

A lightweight chatbot developed for Uganda Christian University that uses zero-shot classification with Sentence-Transformers (MiniLM-v2) to understand and respond to user queries without requiring model training.

The chatbot is accessible through a web interface built with Streamlit, as well as a command-line interface for testing and development.

⸻

Table of Contents
	•	Overview￼
	•	Features￼
	•	Tech Stack￼
	•	Project Structure￼
	•	Installation￼
	•	Usage￼
	•	Example Queries￼
	•	How It Works￼
	•	Customization￼
	•	Troubleshooting￼
	•	Future Improvements￼
	•	License￼

⸻

Overview

This project implements a zero-shot chatbot that uses semantic similarity to match user queries with predefined intents. Instead of training a model, it relies on pre-trained embeddings to determine the closest matching response.

⸻

Features
	•	Zero-shot intent classification (no training required)
	•	Fast response time using MiniLM-v2
	•	Streamlit-based web interface
	•	Command-line interface support
	•	Session-based chat history
	•	Easy to extend using a JSON file

⸻

Tech Stack
	•	Python 3.x
	•	Sentence-Transformers (MiniLM-v2)
	•	Streamlit
	•	JSON (for intent management)

⸻

Project Structure

├── chatbot_zeroshot.py       # Core chatbot logic
├── app.py                    # Streamlit web interface
├── intents.json              # Intents and responses
├── requirements_zeroshot.txt # Dependencies
├── setup_zeroshot.sh         # Setup script


⸻

Installation

Clone the repository:

git clone https://github.com/your-username/ucu-chatbot.git
cd ucu-chatbot

Run the setup script:

bash setup_zeroshot.sh


⸻

Usage

Web Interface (Recommended)

source venv/bin/activate
streamlit run app.py

Command Line Interface

source venv/bin/activate
python3 chatbot_zeroshot.py


⸻

Example Queries
	•	Who is the Vice Chancellor of UCU?
	•	Where is Alan Galpin Health Centre located?
	•	Where is Bishop Tucker Building?
	•	What are the library opening hours?
	•	Hello

⸻

How It Works
	1.	The user inputs a query
	2.	The query is converted into an embedding using MiniLM-v2
	3.	The system compares it with stored intent embeddings
	4.	The closest matching intent is selected
	5.	A predefined response is returned

⸻

Customization

To add new functionality:
	1.	Open intents.json
	2.	Add a new intent with:
	•	Example phrases
	•	Corresponding responses
	3.	Save the file and restart the application

No retraining is required.

⸻

Troubleshooting

Port Already in Use

streamlit run app.py --server.port 8502


⸻

Future Improvements
	•	Integration with live university APIs
	•	Database-backed dynamic responses
	•	User authentication system
	•	Deployment to cloud platforms (e.g., AWS, Azure)
	•	Multi-language support

⸻

License

This project is licensed under the MIT License.
