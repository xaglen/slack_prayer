"""
Generates daily prayer reminders.
"""
from __future__ import print_function

import os.path
import random
import logging
import csv
import sys
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

            slack_message = "We pray for two XA members every day, and today we're praying for"
            if len(names[0])==3:
                slack_message+=  " <@"+names[0][2].strip() + ">"
            else:
                slack_message+= " "+names[0][0].strip()+ " " + names[0][1].strip()

            if len(names[1])==3:
                slack_message+= " and <@" + names[1][2].strip() + ">\n\n"
            else:
                slack_message+= " and " + names[1][0].strip()+" "+names[1][1].strip()+"\n\n"

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
       
        slack_message += "Pray this Biblically-inspired prayer over them based on {}\n>{}\n".format(
                prayer[0],
                prayer[1].replace('NAMES', names[0][0].strip()+" and "+names[1][0].strip()))
                # replace NAMES in the CSV passage with the name of the two we're praying for today

        slack_message += ("\nIf as you're praying for them the Lord lays something on your heart "
        "be sure to text it to them! In addition, Chi Alpha nationally urges every student to "
        "*pray Luke 10:2 at 10:02am every day*, \n>Ask the Lord of the harvest to send out "
        "workers into His harvest field.\n\nPray for God to call and equip more laborers (both "
        "globally and specifically here at Stanford)!")
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
