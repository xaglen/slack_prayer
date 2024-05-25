"""
Generates daily prayer reminders.
"""
from __future__ import print_function

import os.path
import random
import logging
import csv
import sys
import requests
from datetime import date
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
#from google.auth.transport.requests import Request
#from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2 import service_account

import settings

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

def main():
    """Retrieves two names from a Google spreadsheet and plugs them into
    text drawn from a CSV file.
    """
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
                print('No data found.')
                return

            names = random.sample(values, 2)

            slack_message = "Pray for "

            if len(names[0])==3:
                slack_message+=  " <@"+names[0][2].strip() + ">"
            else:
                slack_message+= " "+names[0][0].strip()+ " " + names[0][1].strip()

            if len(names[1])==3:
                slack_message+= " and <@" + names[1][2].strip() + ">"
            else:
                slack_message+= " and " + names[1][0].strip()+" "+names[1][1].strip()+""

            slack_message = "\n\nIn addition since it is 10:02am, *pray Luke 10:2*: " \
                            "Ask the Lord of the harvest to send out workers into His harvest field.\n\n" \
                            "As part of that prayer, pray for Chi Alpha members at Stanford to be effective ambassadors for Christ. Pray this Biblically-inspired prayer over the people at the top of this message."

#            for name in names:
#                slack_message += name[0]+' '+name[1]
#                print('%s %s' % (name[0], name[1]))
            #for row in values:
                # Print columns A and E, which correspond to indices 0 and 4.
              #print('%s, %s' % (row[0], row[1]))
        except HttpError as err:
            print(err)

        with open('/www/vhosts/xastanford.org/wsgi/xadb/scripts/pray/prayer.csv', newline='') as csvfile:
            prayers = list(csv.reader(csvfile, delimiter=',', quotechar='"', quoting=csv.QUOTE_ALL, skipinitialspace=True))
            csvfile.close()

        start = date(2022, 6, 12)
        today = date.today()
        which_prayer = (today-start).days % len(prayers)
        #go through the prayers in sequence

        prayer = prayers[which_prayer]

        #prayer = random.choice(prayers)

        if names[0][0].strip() == names[1][0].strip(): #they have the same first name
            name_substitution = names[0][0].strip()+"^2"
        else:
            name_substitution =  names[0][0].strip()+" and "+names[1][0].strip()
       
        slack_message += " based on {reference}\n>{prayer}\n\n".format(
                reference=prayer[0],
                prayer=prayer[1].replace('NAMES', name_substitution))
                # replace NAMES in the CSV passage with the name of the two we're praying for today

        with open('/www/vhosts/xastanford.org/wsgi/xadb/scripts/pray/country_slugs.csv', newline='') as csvfile:
            rows = csv.reader(csvfile, delimiter=',', quotechar='"')
            countries = []
            for row in rows:
                countries.append(row)

        status_code = 404

        while status_code == 404:
            country = random.choice(countries)
            country_name = country[0]
            country_slug = country[1]

            country_url = "https://operationworld.org/locations/{country_slug}/".format(country_slug=country_slug)
            print(country_url)
            r = requests.get(country_url)

            status_code = r.status_code

        slack_message += "On top of that, *pray for God's work around the world*, especially in *{country_name}*. You can learn more about its gospel needs at {country_url}\n\nIf you don't have time for anything else, just cry out, 'God, send gospel workers to {country_name}!'".format(
            country_name=country_name, country_url=country_url)
        print (slack_message)
        
        try:
            resp=client.chat_postMessage(
            channel=settings.SLACK_CHANNEL,
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
    #        print(message)
    #        print(e)
        except TypeError as e:
            message = "TypeError posting prayer focus: {}".format(repr(e))
            logging.info(message)
    #    print(message+": "+repr(e))
        except:
            e = repr(sys.exc_info()[0])
            message = "Error posting prayer focus: {}".format(e)
            logging.info(message)
    #    print(message+": "+e)



if __name__ == '__main__':
    main()
