from __future__ import print_function

import csv
import logging
import os.path
import random
import sys
import urllib.parse
from datetime import date, datetime

import gspread
import requests
import settings
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

logger = logging.getLogger(__name__)
# journald_handler = JournaldLogHandler()
# journald_handler.setFormatter(logging.Formatter('[%(levelname)s] %message)s'))
# logger.addHandler(journald_handler)
logger.setLevel(logging.INFO)

slack_token = settings.SLACK_TOKEN
slack_channel = "#xa-prayer-and-praise"
client = WebClient(token=slack_token)


# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

# The ID and range of a sample spreadsheet.
SAMPLE_SPREADSHEET_ID = settings.GOOGLE_SPREADSHEET_ID
SAMPLE_RANGE_NAME = "April 2022!B2:D50"

SERVICE_ACCOUNT_FILE = "/www/vhosts/xastanford.org/wsgi/xadb/scripts/pray/credentials.json"


def main():
    """Shows basic usage of the Sheets API.
    Prints values from a sample spreadsheet.
    """
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.

    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    else:
        creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        try:
            gc = gspread.authorize(creds)
            sh = gc.open_by_key(SAMPLE_SPREADSHEET_ID)
            result = sh.values_get(SAMPLE_RANGE_NAME)
            values = result.get("values", [])

            if not values:
                print("No data found.")
                return

            names = random.sample(values, 2)

            slackMessage = "We pray for two XA members every day. "

            slackMessage += "Today we're praying for "
            slackMessage += "<@" + names[0][2].strip() + "> and <@" + names[1][2].strip() + ">\n\n"
        #            for name in names:
        #                slackMessage += name[0]+' '+name[1]
        #                print('%s %s' % (name[0], name[1]))
        # for row in values:
        # Print columns A and E, which correspond to indices 0 and 4.
        # print('%s, %s' % (row[0], row[1]))
        except gspread.exceptions.APIError as err:
            print(err)

        with open("/www/vhosts/xastanford.org/wsgi/xadb/scripts/pray/prayer.csv", newline="") as csvfile:
            prayers = list(
                csv.reader(csvfile, delimiter=",", quotechar='"', quoting=csv.QUOTE_ALL, skipinitialspace=True)
            )
            csvfile.close()

        prayer = random.choice(prayers)

        slackMessage += "Pray this Biblically-inspired prayer over them based on {}\n>{}\n".format(
            prayer[0], prayer[1].replace("NAMES", names[0][0].strip() + " and " + names[1][0].strip())
        )

        slackMessage += (
            "\nIf as you're praying for them the Lord lays something on your heart be sure to text it to them!"
        )

        print(slackMessage)

        try:
            resp = client.chat_postMessage(channel=slack_channel, text=slackMessage)
        except SlackApiError as e:
            # You will get a SlackApiError if "ok" is False
            message = "Slack error posting prayer focus"
            logger.info(message)
            logger.info(e)
            logger.info(e.response)
        #        print(message)
        #        print(e)
        except TypeError as e:
            message = "TypeError posting prayer focus"
            logger.info(message + ": " + repr(e))
        #    print(message+": "+repr(e))
        except:
            e = repr(sys.exc_info()[0])
            message = "Error posting prayer focus"
            logger.info(message + ": " + e)
    #    print(message+": "+e)


if __name__ == "__main__":
    main()
