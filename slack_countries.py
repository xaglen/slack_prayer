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
from time import sleep

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

 #   with open('countries.csv', newline='') as csvfile:
 #       rows = csv.reader(csvfile, delimiter=',', quotechar='"')
 #       new_rows = []
 #       for row in rows:
 #           country_name = row[3]
 #           country_slug = country_name.lower().strip()
 #           country_slug = re.sub(r'[\s_-]+', '-', country_slug)
 #           new_rows.append([country_name,country_slug])

 #   with open('country_slugs.csv', 'w', newline='') as csvfile:
 #       writer = csv.writer(csvfile, delimiter=',',
 #                               quotechar='"', quoting=csv.QUOTE_MINIMAL)
 #       for row in new_rows:
 #           writer.writerow(row)

    with open('country_slugs.csv', newline='') as csvfile:
        rows = csv.reader(csvfile, delimiter=',', quotechar='"')
        countries = []
        for row in rows:
            countries.append(row)
            #country_name = row[0]
            #country_slug = row[1]
            #country_url = "https://operationworld.org/locations/{country_slug}/".format(country_slug=country_slug)
            #r = requests.get(country_url)
            #if r.status_code==404:
            #    print(country_name)
            #else:
            #    print('+')
            #sleep(2)

    status_code = 404

    while status_code == 404:
        country = random.choice(countries)
        country_name = country[0]
        country_slug = country[1]

        country_url="https://operationworld.org/locations/{country_slug}/".format(country_slug=country_slug)
        print(country_url)
        r = requests.get(country_url)

        status_code = r.status_code

    slack_message = "In honor of Luke 10:2, *every night at 10:02pm we pray for God to raise up global laborers.* Tonight we are praying for God to raise up workers for *{country_name}*. You can learn more about its gospel needs at {country_url}\n\nIf you don't have time for anything else, just cry out, 'God, send gospel workers to {country_name}!'".format(country_name=country_name, country_url=country_url)
    #print(slack_message)

    try:
        resp=client.chat_postMessage(
            channel=settings.SLACK_CHANNEL,
            #channel="#xa-test",
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
