"""
Generates an list of those who were not prayed for during the previous month summmary for Slack.
"""
#import json
import pprint
import logging
import sys, os
import re
import time
from collections import Counter
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2 import service_account

#from systemd.journal import JournaldLogHandler

import settings


def fetch_candidates():
    candidates = set()
    client = WebClient(token=settings.SLACK_TOKEN)
    try:
        resp = client.conversations_members(
            channel="C03PWTSSE04", #xa-members
            limit=200 #max 1000, default 100
        )
    except SlackApiError as e:
        # You will get a SlackApiError if "ok" is False
        message = "\nSlackApiError: Slack error retrieving members\n"
        message += " " + repr(e) + "\n"
        message += " " + repr(e.response) + "\n"
        print(message)
        print(e)

    print("{} candidates".format(len(candidates)))

    for member in resp['members']:
        #TODO remove Scorekeeper / bots in general / Glen
        candidates.add(member)

    return candidates

def fetch_activity(client = None, channel=None, open_season=None, close_season=None):
    """
    Retrieves posts from slack channel.

    Retrieves all posts from the given slack channel between open_season and close_season.
    """
    try:
        #data = json.loads(request.body.decode('utf-8'))
        result = client.conversations_history(
                channel=channel,
                oldest=open_season.timestamp(),
                latest=close_season.timestamp())
        conversation_history = []
        conversation_history += result['messages']
        ts_list = [item['ts'] for item in conversation_history]
        last_ts = ts_list[:-1]
        while result['has_more']:
            result = client.conversations_history(
                channel=channel,
                cursor=result['response_metadata']['next_cursor'],
                latest=last_ts,
                oldest=open_season.timestamp())
            conversation_history+=result['messages']
         #logger.info(repr(data))
    except SlackApiError as e:
        print(repr(e))
        return conversation_history

    return conversation_history


def main():
    """
    Generates a post for Slack based upon history in the channel.
    """
    start_time = time.time()

    logger = logging.getLogger(__name__)
    #journald_handler = JournaldLogHandler()
    #journald_handler.setFormatter(logging.Formatter('[%(levelname)s] %message)s'))
    #logger.addHandler(journald_handler)
    logger.setLevel(logging.INFO)

    open_season = settings.OPEN_SEASON
    close_season = settings.CLOSE_SEASON
    season_title = settings.SEASON_TITLE
    season_short_title = settings.SEASON_SHORT_TITLE

    client = WebClient(token=settings.SLACK_TOKEN)

    #pp = pprint.PrettyPrinter(indent=4)
    #pp.pprint(conversation_history)
    #exit()
    #print(conversation_history)

    overlooked=fetch_candidates()

    print("Potential: {}".format(len(overlooked)))
    #print("Type of items in the list: {}".format(type(overlooked[0])))

    conversation_history = fetch_activity(
            client,
            settings.READ_CHANNEL_ID,
            settings.OPEN_SEASON,
            settings.CLOSE_SEASON
            )
    for message in conversation_history:
        ts = int(message['ts'].split('.')[0])
        #timestamp = datetime.fromtimestamp(ts)
        if open_season.timestamp() <= ts < close_season.timestamp():
            #TODO check if posted by prayer bot
            pprint.pformat(message)
            if 'text' in message:
                if '@' in message['text']:
                    regex = r'\<\@(.*?)\>'
                    hits = re.findall(regex, message['text'])
                    for hit in hits:
                        overlooked.discard(hit)
            #else was a bot

    exit()

    print ("Overlooked: {}".format(len(overlooked)))
    #print("Type of hits attempting to remove from the list: {}".format(type(hit)))
    #print("Type of users attempting to remove from the list: {}".format(type(message['user'])))

    final_overlooked = set()

    for person in overlooked:
        print(get_name(person))
        final_overlooked.add("<@" + person + ">")

    try:
        title = "Overlooked In I-See-You: "+ season_title
        resp=client.chat_postMessage(
            channel=settings.OVERLOOKED_WRITE_CHANNEL_ID,
            text="Not tagged nor taggers in I See You last month: " + " ".join(final_overlooked)
        )
    except SlackApiError as e:
        # You will get a SlackApiError if "ok" is False
        message = "\nSlackApiError: Slack error posting tally\n"
        message += " "+repr(e)+"\n"
        message += " "+repr(e.response)+"\n"
        logger.info(message)
        print(message)
        print(e)
    except TypeError as e:
        message = "TypeError posting tally: "+ repr(e)
        logger.info(message)
        #    print(message+": "+repr(e))
    except:# pylint: disable=bare-except
        e = repr(sys.exc_info()[0])
        message = "Error posting tally: "+ e
        logger.info(message)

    try: # pylint: disable=bare-except
        print(message)
    except: # pylint: disable=bare-except
        pass

    execution_time = (time.time() - start_time)
    print('Execution time in seconds: ' + str(execution_time))

if __name__ == '__main__':
    main()

