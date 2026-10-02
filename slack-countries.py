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
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

_sys.path.insert(0, "/www/vhosts/xastanford.org/wsgi/xadb")
import os as _os

_os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mysite.settings")
import django

django.setup()

try:
    # XADB deployment: persistent log in /var/log/xadb + Sentry alerts on errors.
    # After django.setup(), so this Sentry init (with the cron_script tag) wins.
    _sys.path.insert(0, "/www/vhosts/xastanford.org/wsgi/xadb/scripts")
    import cron_logging

    cron_logging.setup("pray-countries")
except ImportError:
    logging.basicConfig(level=logging.INFO)

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
                logging.warning(f"Operation World page layout changed? no div.the-content in div.w-prayer at {url}")
                return None
        else:
            logging.warning(f"Operation World page layout changed? no div.w-prayer at {url}")
            return None

    except requests.RequestException as e:
        logging.warning(f"Error fetching Operation World paragraph: {e}")
        return None
    except Exception as e:
        logging.exception(f"Error parsing Operation World paragraph from {url}")
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
            logging.error("No country with a live Operation World page after fallback; not posting")
            sys.exit(1)

    logging.info(
        f"Picked {country_name} ({'weighted pool of ' + str(len(pool)) if pool else 'no JP pool'}, "
        f"region of the week: {country_data.continent_of_the_week()}, OW status {status_code})"
    )
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

    try:
        resp = client.chat_postMessage(
            channel=settings.SLACK_PRAYER_CHANNEL,
            # channel="#xa-test",
            text=fallback_text,
            blocks=payload["blocks"],
        )
    except SlackApiError as e:
        # You will get a SlackApiError if "ok" is False
        logging.error(f"Slack error posting prayer focus: {e.response.get('error')}", exc_info=True)
        logging.debug(payload)
        sys.exit(1)
    except Exception:
        logging.exception("Error posting prayer focus")
        sys.exit(1)
    logging.info(
        f"Posted {country_name} to {settings.SLACK_PRAYER_CHANNEL} (ts {resp.get('ts')}, "
        f"OW paragraph {len(prayer_paragraph or '')} chars, JP facts {'yes' if facts_lines else 'no'})"
    )
    logging.debug(payload)

    try:
        from people.models import CountryPrayer

        CountryPrayer.objects.create(
            country_name=country_name,
            country_url=country_url,
            wikipedia_url=wikipedia_url,
            prayer_text=prayer_paragraph or "",
        )
    except Exception:
        # the post is out; without the row /pray/ misses it and recency dedup may repeat the country
        logging.exception(f"Posted {country_name} but could not save its CountryPrayer row")
        sys.exit(1)


if __name__ == "__main__":
    main()
