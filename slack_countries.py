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
import re
import requests

import settings

logging.basicConfig(
        filename="pray.log.txt", 
        format='%(asctime)s %(levelname)-8s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        encoding="utf-8", 
        level=logging.INFO)
logging.info("NEW COUNTRIES RUN")

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

    with open('countries.csv', newline='') as csvfile:
        countries = csv.reader(csvfile, delimiter=',', quotechar='"')

    status_code = 404

    while status_code == 404:
        country = random.sample(countries,1)
        country_name=country[3]

        country_slug = country_name.lower().strip()
        country_slug = re.sub(r'[\s_-]+', '-', country_slug)

        country_url="https://operationworld.org/locations/{country_slug}/".format(country_slug=country_slug)

        r = requests.get(country_url)

        status_code = r.status_code

    slack_message = "In honor of Luke 10:2, every night at 10:02pm we pray for God to raise up laborers to make disciples around the world. Tonight we are praying for God to raise up disciplemakers to reach {country_name}. You can learn more about its gospel needs at {country_url}".format(country_name=country_name, country_url=country_url)

    try:
        resp=client.chat_postMessage(
        #channel=settings.SLACK_CHANNEL,
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