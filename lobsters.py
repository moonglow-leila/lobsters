import os
import json
from playwright.sync_api import sync_playwright, Playwright
import requests
from datetime import datetime, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build

import modal

volume = modal.Volume.from_name("cousin-lobster-credentials")
app = modal.App("cousin-lobster")

image = modal.Image.debian_slim().pip_install(
    "google-api-python-client",
    "playwright",
    "requests"
).run_commands("playwright install chromium")

def validate_locations(locations):
    """Validates and filters location data structure"""
    if not isinstance(locations, dict):
        return None
        
    filtered_locations = {}
    for date, events in locations.items():
        # Validate date format (MM-DD)
        if not isinstance(date, str) or not len(date.split('-')) == 2:
            return None
            
        # Filter and validate events
        sf_events = []
        for event in events:
            if not all(key in event for key in ['title', 'location', 'maps_url', 'start_time', 'end_time']):
                return None
                
            if 'San Francisco' in event['title']:
                sf_events.append(event)
                
        if sf_events:
            filtered_locations[date] = sf_events

    print(sf_events)
            
    return filtered_locations if filtered_locations else None

def extract_sf_locations(playwright: Playwright):
    """Extract SF locations using Playwright and Claude"""
    try:
        # Connect to Browserbase
        chromium = playwright.chromium
        browser = chromium.connect_over_cdp(
            f'wss://connect.browserbase.com?apiKey={os.environ["BROWSERBASE_API_KEY"]}'
        )
        context = browser.contexts[0]
        page = context.pages[0]

        # Navigate to website
        page.goto('https://www.cousinsmainelobster.com/locations/san-francisco-bay-area-ca/')
        page.wait_for_selector('.detail-schedule')
        schedule_html = page.eval_on_selector('.detail-schedule', 'el => el.outerHTML')
        
        # Call Claude API
        headers = {
            'Content-Type': 'application/json',
            'x-api-key': os.environ["ANTHROPIC_API_KEY"],
            'anthropic-version': '2023-06-01'
        }
        
        prompt = f"""Given the HTML schedule below, extract the San Francisco locations and format them as a JSON object. 
        The dates should be in MM-DD format as keys, and each date should have an array of event objects.
        Each event object should include:
        - title
        - location
        - maps_url
        - start_time (in 24-hour format)
        - end_time (24-hour format)
        
        HTML:
        {schedule_html}
        
        Please format the response as a valid JSON object."""

        response = requests.post(
            'https://api.anthropic.com/v1/messages',
            headers=headers,
            json={
                "messages": [{"role": "user", "content": prompt}],
                "model": "claude-3-sonnet-20240229",
                "max_tokens": 4096,
                "temperature": 0
            }
        )
        
        result = response.json()
        locations = json.loads(result['content'][0]['text'])
        print(f'Locations: {locations}')
        
        # Add validation
        validated_locations = validate_locations(locations)
        print(f'Validated locations: {validated_locations}')
        if not validated_locations:
            print("Invalid or empty location data received")
            return None
            
        browser.close()
        return validated_locations
        
    except Exception as e:
        print(f"Error extracting locations: {str(e)}")
        if 'browser' in locals():
            browser.close()
        return None


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
                raise Exception("Saved calendar not found, and creating a new one is not allowed.")
            
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

    def create_events(self, schedule, year=2024):
        """Creates calendar events for SF food truck locations."""
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

@app.function(
    image=image,
    volumes={"/credentials": volume},
    schedule=modal.Cron("0 8 * * 6"),
    secrets=[modal.Secret.from_name("cousin-lobster-secrets")]    
)
def update_calendar():
    # Extract locations
    with sync_playwright() as playwright:
        sf_locations = extract_sf_locations(playwright)
    
    if not sf_locations:
        print("Failed to extract locations. Calendar not updated.")
        return
    
    # Update calendar
    SERVICE_ACCOUNT_PATH = "/credentials/service-account.json"
    CALENDAR_ID_PATH = "/credentials/calendar_id.txt"
    
    calendar = FoodTruckCalendar(service_account_path=SERVICE_ACCOUNT_PATH)
    calendar.authenticate()
    calendar.get_or_create_calendar(calendar_id_path=CALENDAR_ID_PATH)
    calendar.create_events(schedule=sf_locations)
    
    print("Calendar successfully updated with new locations")

# For local testing
if __name__ == "__main__":
    update_calendar.local()
