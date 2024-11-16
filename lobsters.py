from google.oauth2 import service_account
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from datetime import datetime, timedelta
import os.path

import modal

app = modal.App("cousin-lobster")

volume = modal.Volume.from_name("cousin-lobster-credentials")
stub = modal.App("cousin-lobster")

image = modal.Image.debian_slim().pip_install(
    "google-api-python-client"  # Note: we don't need oauth2client anymore
)

class FoodTruckCalendar:
    def __init__(self, service_account_path='service-account.json'):
        self.SCOPES = [
            'https://www.googleapis.com/auth/calendar',
            'https://www.googleapis.com/auth/calendar.events',
            'https://www.googleapis.com/auth/calendar.calendarlist'
        ]
        self.service_account_path = service_account_path
        self.creds = None
        self.service = None
        self.calendar_id = None
        
    def authenticate(self):
        """Handles authentication with Google Calendar API using service account."""
        self.creds = service_account.Credentials.from_service_account_file(
            self.service_account_path, 
            scopes=self.SCOPES
        )
        self.service = build('calendar', 'v3', credentials=self.creds)
        
    def get_or_create_calendar(self, calendar_id_path='calendar_id.txt'):
        """Gets existing food truck calendar or creates a new one."""
        if os.path.exists(calendar_id_path):
            with open(calendar_id_path, 'r') as f:
                self.calendar_id = f.read().strip()
            try:
                self.service.calendars().get(calendarId=self.calendar_id).execute()
                print(f"Using existing calendar: {self.calendar_id}")
                return
            except Exception:
                print("Saved calendar not found, creating new one...")
                
        calendar_body = {
            'description': "Cousin's Lobster Locations",
            'summary': "Cousin's Lobster Schedule",
            'timeZone': 'America/Los_Angeles'
        }
        
        try:
            created_calendar = self.service.calendars().insert(body=calendar_body).execute()
            self.calendar_id = created_calendar['id']
            with open(calendar_id_path, 'w') as f:
                f.write(self.calendar_id)
            print(f"Created new calendar with ID: {self.calendar_id}")
        except Exception as e:
            print(f"Error creating calendar: {e}")
            raise

    def clear_existing_events(self, start_date, end_date):
        """Clears existing events in the specified date range."""
        try:
            events = self.service.events().list(
                calendarId=self.calendar_id,
                timeMin=start_date.isoformat() + 'Z',
                timeMax=end_date.isoformat() + 'Z'
            ).execute()
            
            for event in events.get('items', []):
                self.service.events().delete(
                    calendarId=self.calendar_id,
                    eventId=event['id']
                ).execute()
            print(f"Cleared existing events between {start_date} and {end_date}")
        except Exception as e:
            print(f"Error clearing events: {e}")

    def create_events(self, year=2024):
        """Creates calendar events for SF food truck locations."""
        schedule = {
            "11-16": [
                {
                    "title": "Pier 41 San Francisco (Cart Only)",
                    "location": "Pier 41 Marine Terminal, The Embarcadero, San Francisco, CA 94133, USA",
                    "maps_url": "https://maps.google.com/?q=Pier 41 Marine Terminal, The Embarcadero, San Francisco, CA 94133, USA",
                    "start_time": "11:30",
                    "end_time": "20:00"
                }
            ],
            "11-19": [
                {
                    "title": "San Francisco: Equator Coffees",
                    "location": "2 Marina Blvd, San Francisco, CA 94123, USA",
                    "maps_url": "https://maps.google.com/?q=2 Marina Blvd, San Francisco, CA 94123, USA",
                    "start_time": "11:30",
                    "end_time": "14:30"
                },
                {
                    "title": "San Francisco: SPARK Social SF",
                    "location": "601 Mission Bay Boulevard North, San Francisco, CA 94158, USA",
                    "maps_url": "https://maps.google.com/?q=601 Mission Bay Boulevard North, San Francisco, CA 94158, USA",
                    "start_time": "17:00",
                    "end_time": "20:30"
                }
            ],
            "11-20": [
                {
                    "title": "San Francisco: Intersection of Embarcadero and Market Street",
                    "location": "Market St & Steuart St, San Francisco, CA 94105",
                    "maps_url": "https://maps.google.com/?q=Market St &, Steuart St, San Francisco, CA 94105",
                    "start_time": "11:30",
                    "end_time": "19:30"
                }
            ],
            "11-21": [
                {
                    "title": "San Francisco: Intersection of Embarcadero and Market Street",
                    "location": "Market St & Steuart St, San Francisco, CA 94105",
                    "maps_url": "https://maps.google.com/?q=Market St &, Steuart St, San Francisco, CA 94105",
                    "start_time": "11:30",
                    "end_time": "14:00"
                }
            ],
            "11-22": [
                {
                    "title": "San Francisco: Marina Green",
                    "location": "500 Marina Blvd, San Francisco, CA 94123, USA",
                    "maps_url": "https://maps.google.com/?q=500 Marina Blvd, San Francisco, CA 94123, USA",
                    "start_time": "11:30",
                    "end_time": "19:30"
                },
                {
                    "title": "Pier 41 San Francisco (Cart Only)",
                    "location": "Pier 41 Marine Terminal, The Embarcadero, San Francisco, CA 94133, USA",
                    "maps_url": "https://maps.google.com/?q=Pier 41 Marine Terminal, The Embarcadero, San Francisco, CA 94133, USA",
                    "start_time": "11:30",
                    "end_time": "20:00"
                }
            ]
        }
        
        # Calculate date range for clearing existing events
        dates = sorted(schedule.keys())
        start_date = datetime(year, int(dates[0].split('-')[0]), 
                            int(dates[0].split('-')[1]))
        end_date = datetime(year, int(dates[-1].split('-')[0]), 
                          int(dates[-1].split('-')[1])) + timedelta(days=1)
        
        self.clear_existing_events(start_date, end_date)
        
        for date, events in schedule.items():
            month, day = date.split('-')
            for event in events:
                start_datetime = datetime(year, int(month), int(day),
                                       *map(int, event['start_time'].split(':')))
                end_datetime = datetime(year, int(month), int(day),
                                     *map(int, event['end_time'].split(':')))
                
                description = (
                    f"📍 {event['location']}\n\n"
                    f"🗺 Maps: {event['maps_url']}"
                )
                
                event_body = {
                    'summary': event['title'],
                    'location': event['location'],
                    'description': description,
                    'start': {
                        'dateTime': start_datetime.isoformat(),
                        'timeZone': 'America/Los_Angeles',
                    },
                    'end': {
                        'dateTime': end_datetime.isoformat(),
                        'timeZone': 'America/Los_Angeles',
                    },
                    'reminders': {
                        'useDefault': True
                    },
                    'source': {
                        'url': event['maps_url'],
                        'title': 'Open in Google Maps'
                    }
                }
                
                try:
                    created_event = self.service.events().insert(
                        calendarId=self.calendar_id, body=event_body).execute()
                    print(f"Created event: {created_event.get('htmlLink')}")
                except Exception as e:
                    print(f"Error creating event: {e}")

@stub.function(
    image=image,
    volumes={"/credentials": volume},
    schedule=modal.Cron("0 8 * * 1,4")
)
def update_calendar():
    SERVICE_ACCOUNT_PATH = "/credentials/service-account.json"
    CALENDAR_ID_PATH = "/credentials/calendar_id.txt"
    
    calendar = FoodTruckCalendar(service_account_path=SERVICE_ACCOUNT_PATH)
    calendar.authenticate()
    calendar.get_or_create_calendar(calendar_id_path=CALENDAR_ID_PATH)
    calendar.create_events()