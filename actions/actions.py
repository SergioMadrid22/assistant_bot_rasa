from __future__ import print_function

from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import AllSlotsReset

import datetime
from datetime import datetime, timedelta
import os
import os.path
import pickle
import pytz
import feedparser
import requests
import base64

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import google.generativeai as genai

SCOPES = ['https://www.googleapis.com/auth/calendar']
CREDENTIALS_FILE = 'credentials.json'

WEATHER_API_KEY = "bb65292bef196f2811b56c0f7f6dbe5c"
WEATHER_API_URL = "https://api.openweathermap.org/data/2.5/weather"

GOOGLE_AI_API = "AIzaSyCdkSiD-k9qVDWKlEy8i7Jjrz3DrVopA5o"

def get_calendar_service():
    creds = None
    # The file token.pickle stores the user's access and refresh tokens
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
            print("Loaded credentials from token.pickle")

    # If no valid credentials, let the user log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            print("Credentials refreshed")
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=6060)

            print("Obtained new credentials")

        # Save the credentials for the next run
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
            print("Saved new credentials to token.pickle")

    try:
        service = build('calendar', 'v3', credentials=creds)
        return service
    except Exception as e:
        print(f"An error occurred while building the service: {e}")
        return None

def add_event(service, event_name: Text, event_start: datetime, event_end: datetime):
    """
    Adds a new event to Google Calendar.
    """
    try:
        new_event = {
            'summary': event_name,
            'location': "Default Location",  # Customize as needed
            'description': "Automatically added event",
            'start': {
                'dateTime': event_start.isoformat(),
                'timeZone': 'Europe/Madrid',
            },
            'end': {
                'dateTime': event_end.isoformat(),
                'timeZone': 'Europe/Madrid',
            },
            'reminders': {
                'useDefault': True,
            },
        }
        created_event = service.events().insert(calendarId='primary', body=new_event).execute()
        print(f"Created event: {created_event.get('htmlLink')}")
        return created_event
    except HttpError as error:
        print(f"An error occurred while adding the event: {error}")
        return None

def get_events(service, time_min: Text, time_max: Text) -> List[Dict[str, Any]]:
    """
    Retrieves events within the specified time range.
    """
    try:
        events_result = service.events().list(
            calendarId='primary',
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        events = events_result.get('items', [])
        return events
    except HttpError as error:
        print(f"An error occurred while fetching events: {error}")
        return []

class CreateEvent(Action):

    def name(self) -> Text:
        return "action_create_event"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        event_name = tracker.get_slot('event')
        time_str = tracker.get_slot('time')

        if not event_name or not time_str:
            dispatcher.utter_message(text="Por favor, proporciona tanto el nombre del evento como la hora.")
            return [AllSlotsReset()]

        try:
            # Parse the time slot to a datetime object
            event_start_time = datetime.strptime(time_str, '%d/%m/%Y %H:%M')

            # Assign timezone to the datetime object
            tz = pytz.timezone('Europe/Madrid')
            event_start_time = tz.localize(event_start_time)

            # Calculate event end time (1 hour duration)
            event_end_time = event_start_time + timedelta(hours=1)

            # Define time range for conflict checking (same as event time)
            time_min = event_start_time.isoformat()
            time_max = event_end_time.isoformat()

            # Initialize Google Calendar API
            service = get_calendar_service()
            if not service:
                dispatcher.utter_message(text="No se pudo inicializar el servicio de Google Calendar.")
                return [AllSlotsReset()]

            # Retrieve existing events in the desired time slot
            existing_events = get_events(service, time_min, time_max)

            # Initialize conflict flag
            conflict = False
            conflicting_event = None

            # Check for any existing event in the time slot
            if existing_events:
                conflict = True
                conflicting_event = existing_events[0]  # Get the first conflicting event

            if conflict:
                event_start = conflicting_event['start'].get('dateTime', conflicting_event['start'].get('date'))
                dispatcher.utter_message(
                    text=f"No se puede crear un nuevo evento porque el horario ya está ocupado por '{conflicting_event['summary']}' a las {event_start}."
                )
            else:
                # No conflict, proceed to add the event
                created_event = add_event(service, event_name, event_start_time, event_end_time)
                if created_event:
                    dispatcher.utter_message(
                        text=f"Evento '{event_name}' añadido exitosamente a tu calendario en la fecha {event_start_time.strftime('%d/%m/%y %H:%M:%S')}."
                    )
                else:
                    dispatcher.utter_message(text="No se pudo añadir el evento debido a un error interno.")

        except ValueError as ve:
            dispatcher.utter_message(text=f"Error de formato: {ve}. Por favor, asegúrate de que la hora esté en el formato 'DD/MM/YYYY HH:MM'.")
        except Exception as e:
            # Handle unexpected errors
            dispatcher.utter_message(text=f"Ocurrió un error inesperado: {str(e)}")

        # Reset slots after execution
        return [AllSlotsReset()]

class GetEvents(Action):

    def name(self) -> Text:
        return "action_get_events"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        try:
            service = get_calendar_service()
            if not service:
                dispatcher.utter_message(text="No se pudo inicializar el servicio de Google Calendar.")
                return []

            now = datetime.now(pytz.timezone('Europe/Madrid')).isoformat()
            # Fetch events for the next year to ensure coverage
            events = get_events(service, now, (datetime.utcnow() + timedelta(days=365)).isoformat() + 'Z')

            if not events:
                dispatcher.utter_message(text="No tienes eventos próximos.")
                return []

            messages = []
            for event in events:
                start = event['start'].get('dateTime', event['start'].get('date'))
                summary = event.get('summary', 'No Title')
                messages.append(f"{start}: {summary}")

            events_message = "\n".join(messages)
            dispatcher.utter_message(text=f"Tus próximos eventos:\n{events_message}")

        except Exception as e:
            dispatcher.utter_message(text=f"Ocurrió un error al obtener los eventos: {str(e)}")

        return []


class GetNews(Action):
    def name(self) -> str:
        return "action_get_news"

    def run(self, dispatcher: CollectingDispatcher, tracker, domain):
        feed = feedparser.parse("https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada")
        
        articles = feed.entries[:5]  # Get the latest 5 articles
        news_list = "\n".join([f"- {article.title}: {article.link}" for article in articles])
        dispatcher.utter_message(text=f"Últimas noticias:\n{news_list}")
        return []



class GetWeather(Action):

    def name(self) -> Text:
        return "action_get_weather"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        # Get city slot from user input
        city = tracker.get_slot("city")

        if not city:
            dispatcher.utter_message(text="Por favor, dime la ciudad para la que te gustaría saber el clima.")
            return []

        try:
            # Make API request to get weather data
            params = {
                "q": city,
                "appid": WEATHER_API_KEY,
                "units": "metric"  # Use metric units (Celsius)
            }
            response = requests.get(WEATHER_API_URL, params=params)
            data = response.json()

            if response.status_code == 200:
                # Extract relevant data
                temperature = data["main"]["temp"]
                weather_description = data["weather"][0]["description"]
                city_name = data["name"]
                country = data["sys"]["country"]

                # Respond to the user
                dispatcher.utter_message(
                    text=f"El clima actual en {city_name}, {country} es {weather_description} con una temperatura de {temperature}°C."
                )
            else:
                dispatcher.utter_message(
                    text=f"Lo siento, no pude encontrar información del clima para {city}. Por favor, verifica el nombre de la ciudad y vuelve a intentarlo."
                )

        except Exception as e:
            dispatcher.utter_message(
                text=f"Ocurrió un error al obtener el clima: {str(e)}"
            )

        return [AllSlotsReset()]


class ActionAskGemini(Action):
    def name(self) -> str:
        return "action_ask_gemini"
    
    def run(self, dispatcher, tracker, domain):
        # Get the user's message from the tracker
        user_message = tracker.latest_message.get('text')

        genai.configure(api_key=GOOGLE_AI_API)
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(user_message)
        print(response.text)
        dispatcher.utter_message(text=response.text)
        return []
    
class ActionGenerateImage(Action):
    def name(self) -> str:
        return "action_generate_image"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[str, Any]) -> List[Dict[str, Any]]:
        # Get the user's prompt from a slot or latest message
        user_prompt = tracker.latest_message.get("text")
        print(f"User prompt: {user_prompt}")
        
        if not user_prompt or "Generar imagen:" not in user_prompt:
            dispatcher.utter_message(text="Por favor, proporciona un texto para generar la imagen.")
            return []
        user_prompt = user_prompt.replace("Generar imagen:", "").strip()
        user_prompt = user_prompt.replace(" ", "-").strip()

        try:
            # Pollinations API endpoint
            pollinations_url = f"https://image.pollinations.ai/prompt/{user_prompt}"
            print(f"Pollinations URL: {pollinations_url}")    
            # The API directly provides an image URL
            response = requests.get(pollinations_url)

            if response.status_code == 200:
                # Send the image back to the user
                dispatcher.utter_message(
                    text="Aquí tienes la imagen generada:",
                    image=pollinations_url
                )
            else:
                dispatcher.utter_message(text="Hubo un error al generar la imagen. Por favor, inténtalo nuevamente.")

        except Exception as e:
            dispatcher.utter_message(text=f"Ocurrió un error inesperado: {str(e)}")

        return []
