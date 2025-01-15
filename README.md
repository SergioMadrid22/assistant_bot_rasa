# Chatbot Deployment Guide

This repository contains all the necessary files to deploy and run a Rasa chatbot integrated with Telegram. The main functionalities of the chatbot are:

- Add and consult events in Google Calendar
- Get the news
- Get the weather in a city
- Ask Gemini LLM
- ASR of audios sent by the user
- TTS of the responses generated when the user sends an audio
- Text-to-Image given a prompt
---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Deployment](#deployment)
- [Usage](#usage)

---

## Prerequisites

Before starting, ensure you have the following installed:

1. **Anaconda**: Install from [here](https://www.anaconda.com/) to manage Python environments.
2. **ngrok**: Download and install ngrok from [here](https://ngrok.com/).

---

## Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/your-username/chatbot-repository.git
   cd chatbot-repository
2. **Create a Python environment**
   ```bash
   conda create --name rasa_env python=3.9 -y
   conda activate rasa_env
3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
4. **Overwrite the Telegram channel integration file**
   ```bash
   cp telegram.py <path-to-your-conda-env>/lib/python3.9/site-packages/rasa/core/channels/

## Deployment

1. **Deploy the Audio Server**
   ```bash
   python audio_server.py
2. **Deploy ngrok server for setting telegram webhook**
   ```bash
   ngrok http 5005
   ```
   Copy the HTTPS URL provided by ngrok and update credentials.yml as follows:
   ```yaml
   telegram:
     access_token: "<your-telegram-bot-token>"
     verify: "<your-bot-username>"
     webhook_url: "https://<ngrok-url>/webhooks/telegram/webhook"
3. **Deploy the actions server**
   ```bash
   rasa run actions
4. **Train the Chatbot**
   ```bash
   rasa train
5. **Deploy the chatbot**
   ```bash
   rasa run --enable-api --cors "*" --debug

## Usage
1. Add the Chatbot to your Telegram account using the Chatbot username "Calendar_smadper_bot"
2. Start chatting with the Chatbot