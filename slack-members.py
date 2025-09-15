"""
Generates daily prayer reminders.
"""
from __future__ import print_function

import os.path
import logging
import csv
import sys
import requests
from icecream import ic
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
#from google.auth.transport.requests import Request
#from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2 import service_account
from datetime import date, datetime, timedelta, timezone
from slack_sdk.errors import SlackApiError
import time
import random

import settings

# uncomment the next line in production
ic.disable()

logging.basicConfig(
        filename="pray.log.txt", 
        format='%(asctime)s %(levelname)-8s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        encoding="utf-8", 
        level=logging.INFO)
logging.info("NEW RUN")

#logger = logging.getLogger(__name__)
#journald_handler = JournaldLogHandler()
#journald_handler.setFormatter(logging.Formatter('[%(levelname)s] %message)s'))
#logger.addHandler(journald_handler)
#logger.setLevel(logging.INFO)

client = WebClient(token=settings.SLACK_TOKEN)

class SlackMentionTracker:
    def __init__(self):
        self.client = client

    def scan_channel_mentions(self, channel_id, days=30):
        """
        Scan a Slack channel for user mentions in the last N days
        Returns a dictionary with user IDs and their last mention timestamps
        """
        # Calculate the cutoff timestamp (Slack uses Unix timestamps)
        cutoff_timestamp = (datetime.now(timezone.utc) - timedelta(days=days)).timestamp()

        last_mentions = {}
        cursor = None

        ic(f"Scanning channel for mentions in the last {days} days...")

        try:
            while True:
                # Get messages from the channel
                response = self.client.conversations_history(
                    channel=channel_id,
                    oldest=cutoff_timestamp,
                    limit=1000,  # Max per request
                    cursor=cursor
                )

                messages = response['messages']

                for message in messages:
                    # Check if message contains user mentions
                    message_text = message.get('text', '')
                    message_ts = float(message['ts'])
                    message_dt = datetime.fromtimestamp(message_ts, tz=timezone.utc)

                    # Find user mentions in the format <@U12345678>
                    import re
                    mentions = re.findall(r'<@(U[A-Z0-9]+)>', message_text)

                    for user_id in mentions:
                        # Update if this is the first mention or more recent
                        if user_id not in last_mentions or message_dt > last_mentions[user_id]:
                            last_mentions[user_id] = message_dt

                # Check if there are more messages to fetch
                if not response.get('has_more', False):
                    break

                cursor = response['response_metadata']['next_cursor']

                # Rate limiting - be nice to Slack's API
                time.sleep(1)

        except SlackApiError as e:
            ic(f"Error fetching messages: {e.response['error']}")

        return last_mentions

    def get_user_info(self, user_id):
        """Get user information from Slack"""
        try:
            response = self.client.users_info(user=user_id)
            user = response['user']
            return {
                'id': user['id'],
                'name': user['name'],
                'real_name': user.get('real_name', user['name']),
                'display_name': user['profile'].get('display_name', user['name'])
            }
        except SlackApiError as e:
            print(f"Error getting user info for {user_id}: {e.response['error']}")
            return None

def prioritize_users(users, last_mentions):
    """
    Create prioritized lists of users based on mention history
    Returns tuple of (never_mentioned, mentioned_by_date)
    """
    never_mentioned = []
    mentioned_users = []

    for user_firstname, user_lastname, user_id in users:
        if user_id in last_mentions:
            mentioned_users.append({
                'user_first_name': user_firstname,
                'user_last_name': user_lastname,
                'user_id': user_id,
                'last_mentioned': last_mentions[user_id]
            })
        else:
            never_mentioned.append({
                'user_first_name': user_firstname,
                'user_last_name': user_lastname,
                'user_id': user_id,
                'last_mentioned': None
            })

    # Sort mentioned users by last mention date (oldest first)
    mentioned_users.sort(key=lambda x: x['last_mentioned'])

    return never_mentioned, mentioned_users


def select_weighted_users(prioritized_users, num_users=2):
    """
    Select users with weighted probability favoring those mentioned less recently
    """
    if len(prioritized_users) < num_users:
        return prioritized_users

    weights = []
    for user in prioritized_users:
        if user['last_mentioned'] is None:
            # Never mentioned - highest weight
            weight = 1000
        else:
            # Weight based on days since last mention
            days_since_mention = (datetime.now(timezone.utc) - user['last_mentioned']).days
            weight = max(1, days_since_mention * 10)
        weights.append(weight)

    # Select users without replacement
    selected = []
    users_copy = prioritized_users.copy()
    weights_copy = weights.copy()

    for _ in range(min(num_users, len(users_copy))):
        chosen = random.choices(users_copy, weights=weights_copy, k=1)[0]
        selected.append(chosen)

        # Remove selected user to avoid duplicates
        idx = users_copy.index(chosen)
        users_copy.pop(idx)
        weights_copy.pop(idx)

    return selected


def main():
    """Retrieves two names from a Google spreadsheet and plugs them into
    text drawn from a CSV file.
    """
    tracker = SlackMentionTracker()
    ic("Scanning Slack channel for mentions...")
    mention_history = tracker.scan_channel_mentions(settings.SLACK_MEMBERS_CHANNEL_ID, days=30)

    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.

    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', settings.SCOPES)
    else:
        creds = service_account.Credentials.from_service_account_file(
            settings.SERVICE_ACCOUNT_FILE, scopes=settings.SCOPES)
        try:
            service = build('sheets', 'v4', credentials=creds)
            # Call the Sheets API
            sheet = service.spreadsheets()
            result = sheet.values().get(spreadsheetId=settings.GOOGLE_SPREADSHEET_ID,
                                        range=settings.SPREADSHEET_RANGE_NAME).execute()
            values = result.get('values', [])

            if not values:
                ic('No data found in Google Sheet.')
                logging.error('No data found in Google Sheet')
                return
            ic(values)

            never_mentioned, mentioned_users = prioritize_users(values, mention_history)
            prioritized_users = never_mentioned + mentioned_users

            ic(f"\nResults:")
            ic("- Users with mentions in last 30 days:")
            ic(len(mention_history))
            ic("- Users in Google Sheet:")
            ic(len(values))
            ic("Users never mentioned:")
            ic(len(never_mentioned))
            ic("Users previously mentioned")
            ic(len(mentioned_users))

            # Show top 10 prioritized users
            ic(f"\n=== TOP 10 PRIORITIZED USERS ===")
            for i, user in enumerate(prioritized_users[:10]):
                if user['last_mentioned']:
                    days_ago = (datetime.now(timezone.utc) - user['last_mentioned']).days
                    msg = f"{i + 1}. {user['user_first_name']} {user['user_last_name']} (last mentioned {days_ago} days ago)"
                    ic(msg)
                else:
                    msg =f"{i + 1}. {user['user_first_name']} {user['user_last_name']} (never mentioned)"
                    ic(msg)

            # Select 2 users for tagging
            names = select_weighted_users(prioritized_users, 2)

            ic(names)

            slack_message = "Pray for"

            slack_message+=f" <@{names[0]['user_id'].strip()}>"
            slack_message+=f" and <@{names[1]['user_id'].strip()}>"

            slack_message += ". You can pray for them however you want, but consider learning to pray Scripturally by modeling your prayer on "

        except HttpError as err:
            ic(err)

        with open('/www/vhosts/xastanford.org/wsgi/xadb/scripts/pray/prayer.csv', newline='') as csvfile:
            prayers = list(csv.reader(csvfile, delimiter=',', quotechar='"', quoting=csv.QUOTE_ALL, skipinitialspace=True))
            csvfile.close()

        start = date(2022, 6, 12)
        today = date.today()
        which_prayer = (today-start).days % len(prayers)
        #go through the prayers in sequence

        prayer = prayers[which_prayer]

        #prayer = random.choice(prayers)

        if names[0]['user_first_name'].strip() == names[1]['user_first_name'].strip(): #they have the same first name
            name_substitution = names[0]['user_first_name'].strip()+"^2"
        else:
            name_substitution =  names[0]['user_first_name'].strip()+" and "+names[1]['user_first_name'].strip()
       
        slack_message += "{reference}, like so:\n\n>{prayer}".format(
                reference=prayer[0],
                prayer=prayer[1].replace('NAMES', name_substitution))
                # replace NAMES in the CSV passage with the name of the two we're praying for today

        slack_message += "\n\n_note that the Bible prayers repeatedly focus on (1) personal spiritual growth and blessing (2) fruitful evangelism and (3) unity in the Body - this should shape our regular prayer lives_"

        ic(slack_message)

        try:
            resp=client.chat_postMessage(
            channel=settings.SLACK_MEMBERS_CHANNEL,
            text=slack_message
            )
            logging.info("SUCCESSFULLY POSTED")
            logging.info(slack_message)
        except SlackApiError as e:
        # You will get a SlackApiError if "ok" is False
            message = "Slack error posting prayer focus"
            logging.info(message)
            logging.info(e)
            logging.info(e.response)
    #        ic(message)
    #        ic(e)
        except TypeError as e:
            message = "TypeError posting prayer focus: {}".format(repr(e))
            logging.info(message)
    #    ic(message+": "+repr(e))
        except:
            e = repr(sys.exc_info()[0])
            message = "Error posting prayer focus: {}".format(e)
            logging.info(message)
    #    ic(message+": "+e)

if __name__ == '__main__':
    main()
