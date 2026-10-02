"""
Generates daily prayer reminders.
"""

from __future__ import print_function

import csv
import logging
import os.path
import random
import re
import sys
import sys as _sys
from datetime import date
from time import sleep
from urllib import parse

import country_data
import requests
import settings
from blockkit import Image, Message, Section
from bs4 import BeautifulSoup
from icecream import ic
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

_sys.path.insert(0, "/www/vhosts/xastanford.org/wsgi/xadb")
import os as _os

_os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mysite.settings")
import django

django.setup()

ic.disable()

logging.basicConfig(
    filename="pray.log.txt",
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    encoding="utf-8",
    level=logging.INFO,
)
logging.info("NEW COUNTRIES RUN")

# logger = logging.getLogger(__name__)
# journald_handler = JournaldLogHandler()
# journald_handler.setFormatter(logging.Formatter('[%(levelname)s] %message)s'))
# logger.addHandler(journald_handler)
# logger.setLevel(logging.INFO)

client = WebClient(token=settings.SLACK_TOKEN)


def get_paragraph_from_operation_world(url):
    try:
        # Send GET request to the website
        response = requests.get(url, timeout=20)
        response.raise_for_status()  # Raises an HTTPError for bad responses

        # Parse the HTML content
        soup = BeautifulSoup(response.content, "html.parser")

        # Find the div with class 'w-prayer'
        w_prayer_div = soup.find("div", class_="w-prayer")

        if w_prayer_div:
            # Find the div with class 'the-content' inside w-prayer
            content_div = w_prayer_div.find("div", class_="the-content")

            if content_div:
                # Extract the text content
                paragraph_text = content_div.get_text(strip=True)
                return paragraph_text
            else:
                ic("Could not find div with class 'the-content'")
                return None
        else:
            ic("Could not find div with class 'w-prayer'")
            return None

    except requests.RequestException as e:
        logging.info(f"Error fetching the website: {e}")
        return None
    except Exception as e:
        logging.info(f"An error occurred: {e}")
        return None


def operation_world_status(url):
    """HTTP status of an Operation World page, or None if it couldn't be reached.
    Only a 404 means the slug is wrong -- an unreachable site still gets posted,
    since the message has a no-paragraph fallback."""
    try:
        return requests.get(url, timeout=20).status_code
    except requests.RequestException as e:
        logging.warning(f"Operation World unreachable for {url}: {e}")
        return None


def main():

    with open("/www/vhosts/xastanford.org/wsgi/xadb/scripts/pray/country_slugs.csv", newline="") as csvfile:
        rows = csv.reader(csvfile, delimiter=",", quotechar='"')
        countries = []
        for row in rows:
            countries.append(row)

    pool = None
    try:
        jp_countries = country_data.get_jp_countries(settings.JOSHUA_PROJECT_API_KEY)
        pool = country_data.build_country_pool(countries, jp_countries)
    except Exception as e:
        logging.warning(f"country_data unavailable, will use unweighted random selection: {e}")
        pool = None

    if "--dry-run" in sys.argv:
        if not pool:
            print("No pool available (Joshua Project fetch/join failed) -- nothing to simulate.")
            return
        import json as _json

        print(_json.dumps(country_data.simulate(pool), indent=2, default=str))
        return

    status_code = 404
    country_name = None
    country_url = None
    wikipedia_url = None
    quick_facts = None
    jp_url = None
    jp_scale_text = None
    jp_scale_image_url = None

    if pool:
        queue = country_data.build_candidate_queue(pool)[: country_data.MAX_ATTEMPTS]
        for candidate in queue:
            country_name = candidate["name"]
            country_url = candidate["country_url"]
            wikipedia_url = candidate["wikipedia_url"]
            quick_facts = candidate.get("quick_facts")
            jp_url = candidate.get("jp_profile_url")
            jp_scale_text = candidate.get("jp_scale_text")
            jp_scale_image_url = candidate.get("jp_scale_image_url")
            status_code = operation_world_status(country_url)
            if status_code != 404:
                break

    if status_code == 404:
        if pool:
            logging.warning("Weighted candidate queue exhausted; falling back to unweighted random selection")
        # the last weighted candidate's Joshua Project facts don't belong to the fallback country
        quick_facts = jp_url = jp_scale_text = jp_scale_image_url = None
        try:
            excluded = country_data.excluded_recent_names()
        except Exception as e:
            logging.warning(f"Could not load recent countries for dedup: {e}")
            excluded = set()
        fallback = [
            row
            for row in countries
            if len(row) >= 2
            and country_data.normalize_name(row[0]) not in country_data.COUNTRY_DENYLIST
            and country_data.normalize_name(row[0]) not in excluded
        ] or countries
        random.shuffle(fallback)
        for country in fallback[: country_data.MAX_ATTEMPTS]:
            country_name = country[0]
            country_url = country_data.operation_world_url(country[1])
            wikipedia_url = country_data.build_wikipedia_url(country_name)
            status_code = operation_world_status(country_url)
            if status_code != 404:
                break
        else:
            logging.warning("No country with a live Operation World page after fallback; not posting")
            print("No country with a live Operation World page after fallback; not posting")
            return

    prayer_paragraph = get_paragraph_from_operation_world(country_url)

    jp_link = f"<{jp_url}|Joshua Project>" if jp_url else "Joshua Project"
    ow_link = f"<{country_url}|Operation World>"

    msg = Message()
    msg.add_block(Section(f"This week intercede for *{country_name}* in your daily prayers. {wikipedia_url}"))

    facts_lines = [
        line for line in (quick_facts, f"Progress level: {jp_scale_text}" if jp_scale_text else None) if line
    ]
    if facts_lines:
        msg.add_block(Section(f"{jp_link} reports:\n>" + "\n>".join(facts_lines)))

    if jp_scale_image_url:
        msg.add_block(
            Image(image_url=jp_scale_image_url, alt_text=f"Progress level: {jp_scale_text}", title=jp_scale_text)
        )

    if prayer_paragraph:
        msg.add_block(Section(f"{ow_link} says:\n>{prayer_paragraph}"))
    else:
        msg.add_block(Section(f"You can learn more about its gospel needs at {ow_link}."))

    msg.add_block(
        Section(
            "This is one of our ways of obeying Luke 10:2 ('ask the Lord of the harvest to send out workers into "
            f"His harvest field'). As you pray for {country_name}, pray especially for God to raise up both "
            "missionaries and local workers."
        )
    )
    payload = msg.build()
    fallback_text = f"This week intercede for {country_name} in your daily prayers. {wikipedia_url}"

    # ic(payload)
    # exit()
    try:
        resp = client.chat_postMessage(
            channel=settings.SLACK_PRAYER_CHANNEL,
            # channel="#xa-test",
            text=fallback_text,
            blocks=payload["blocks"],
        )
        logging.info("SUCCESSFULLY POSTED")
        logging.info(payload)
        from people.models import CountryPrayer

        CountryPrayer.objects.create(
            country_name=country_name,
            country_url=country_url,
            wikipedia_url=wikipedia_url,
            prayer_text=prayer_paragraph or "",
        )
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


if __name__ == "__main__":
    main()
