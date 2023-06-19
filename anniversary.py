"""
Generates birthday daily prayer reminders.
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
logging.info("NEW ANNIVERSARY RUN")

#logger = logging.getLogger(__name__)
#journald_handler = JournaldLogHandler()
#journald_handler.setFormatter(logging.Formatter('[%(levelname)s] %message)s'))
#logger.addHandler(journald_handler)
#logger.setLevel(logging.INFO)

client = WebClient(token=settings.SLACK_TOKEN)

def main():
    """Scans names from a Google spreadsheet looking for birthdays that match today
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
                                        range=settings.ANNIVERSARY_RANGE_NAME).execute()
            values = result.get('values', [])

            if not values:
                print('No data found.')
                return

            anniversaries=[]

            today = date.today()
            print (str(today.month) + "/"+str(today.day))

            for value in values:
                if len(value)>=4:
                    anniversary=value[4].split('/')
                    print(anniversary[0]+"/"+anniversary[1]+" "+value[0])
                    if int(anniversary[0])==today.month and int(anniversary[1])==today.day:
                        anniversaries.append(value)
                        print("ADDED")

            slack_message = "We pray for married couples on their anniversary, and today we're praying for"
            if len(anniversaries)==0:
                exit()
            elif len(anniversaries) == 1:
                slack_message += " *<@{name1}>* and *<@{name2}>*.".format(name1=anniversaries[0][2].strip(),
                                                                          name2=anniversaries[0][3].strip())
                slack_message+=" Happy anniversary! :couple_with_heart: \nPray that this next year is their best one yet!"
            elif len(anniversaries) == 2:
                random.shuffle(anniversaries)
                slack_message += " *<@{name1}>* and *<@{name2}>*.".format(name1=anniversaries[0][2].strip(), name2=anniversaries[0][3].strip())
                slack_message += " as well as *<@{name1}>* and *<@{name2}>*.".format(name1=anniversaries[1][2].strip(), name2=anniversaries[1][3].strip())
                slack_message += " Happy anniversary to all! :couple_with_heart: \nPray that this next year is their best yet!"
            else:
                random.shuffle(anniversaries)
                for anniversary in anniversaries:
                    if anniversary == anniversaries[-1]:
                        slack_message += " *and* <@{name1}>* & *<@{name2}>!".format(name1=anniversary[2].strip(),
                                                                                  name2=anniversary[3].strip())
                    else:
                        slack_message += " <@{name1}>* & *<@{name2}>, ".format(name1=anniversary[2].strip(),
                                                                                  name2=anniversary[3].strip())
                slack_message+=" Happy anniversary to all! Pray amazing blessings over these couples!"

        except HttpError as err:
            print(err)

        print (slack_message)
        
        try:
            resp=client.chat_postMessage(
#            channel=settings.SLACK_CHANNEL,
            channel="#xa-test",
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
