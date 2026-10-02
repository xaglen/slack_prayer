#!/usr/bin/env python3
"""
Script to scan the last ten days of posts in a Slack channel,
count how often members are tagged, and output:
• A list of the three most tagged members.
• A list of members not tagged at all.
"""

import os
import re
import time
from datetime import datetime, timedelta

import settings
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

SLACK_API_TOKEN = settings.SLACK_TOKEN
if not SLACK_API_TOKEN:
    raise ValueError("Please set the SLACK_API_TOKEN environment variable.")

CHANNEL_ID = "C03PWTSSE04"  # Replace with your channel id
# xa-members channel is C03PWTSSE04
client = WebClient(token=SLACK_API_TOKEN)


def safe_slack_api_call(api_func, **kwargs):
    """
    A helper function that calls an API method and handles rate limiting.
    If a rate limit error is encountered (HTTP 429), the function sleeps for the
    number of seconds indicated in the Retry-After header and then retries.
    """
    while True:
        try:
            response = api_func(**kwargs)
            return response
        except SlackApiError as e:
            # Check for rate limiting error
            if e.response.status_code == 429:
                retry_after = int(e.response.headers.get("Retry-After", 1))
                print(f"Rate limited on call to {api_func.__name__}. Sleeping for {retry_after} sec.")
                time.sleep(retry_after)
            else:
                # For other errors, re-raise
                raise e


def get_channel_history(channel_id, oldest_ts):
    """
    Fetches messages in the channel since oldest_ts.
    Returns a list of message objects.
    """
    messages = []
    cursor = None
    while True:
        try:
            response = safe_slack_api_call(
                client.conversations_history, channel=channel_id, oldest=oldest_ts, cursor=cursor, limit=200
            )
        except SlackApiError as e:
            print(f"Error fetching conversation history: {e}")
            break

        messages.extend(response.get("messages", []))
        # Check to see if more pages exist
        cursor = response.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break
    return messages


def get_user_name(user_id):
    """
    Retrieves the display name of a user using users.info.
    Returns None if the user is deleted or is a bot.
    """
    response = safe_slack_api_call(client.users_info, user=user_id)
    user = response.get("user", {})
    if user.get("deleted", False) or user.get("is_bot", False):
        return None
    profile = user.get("profile", {})
    # Prefer display_name; fallback to real_name or simply user_id if neither is set.
    return profile.get("display_name") or profile.get("real_name") or user_id


def get_channel_members(channel_id):
    """
    Get the list of user ids in the specified channel.
    """
    members = []
    cursor = None
    while True:
        try:
            response = safe_slack_api_call(client.conversations_members, channel=channel_id, cursor=cursor, limit=200)
        except SlackApiError as e:
            print(f"Error fetching channel members: {e}")
            break

        members.extend(response.get("members", []))
        cursor = response.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break
    return members


def get_all_users():
    """
    Returns a dictionary mapping user_id -> display name.
    """
    users = {}
    cursor = None
    while True:
        try:
            response = safe_slack_api_call(
                client.users_list,
                cursor=cursor,
                # limit=200
            )
        except SlackApiError as e:
            print(f"Error fetching users list: {e}")
            break

        for user in response.get("members", []):
            # Skip bots and deactivated users if desired.
            if user.get("deleted", False) or user.get("is_bot", False):
                continue
            profile = user.get("profile", {})
            # Use display_name if set, otherwise real_name, otherwise fallback to user id.
            name = profile.get("display_name") or profile.get("real_name") or user.get("id")
            users[user["id"]] = name
            cursor = response.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break
    return users


def main():
    # Calculate the UNIX timestamp for 10 days ago.
    # ten_days_ago = datetime.now() - timedelta(days=10)
    # oldest_ts = time.mktime(ten_days_ago.timetuple())
    # Calculate the UNIX timestamp for 30 days ago.
    thirty_days_ago = datetime.now() - timedelta(days=30)
    oldest_ts = time.mktime(thirty_days_ago.timetuple())

    # Fetch channel messages from the last ten days.
    messages = get_channel_history(CHANNEL_ID, oldest_ts)
    print(f"Fetched {len(messages)} messages from channel {CHANNEL_ID}.")

    # Count tagged occurrences.
    # Slack mentions appear as <@USERID>
    tag_pattern = re.compile(r"<@([A-Za-z0-9]+)>")
    tag_count = {}

    for msg in messages:
        # Only consider messages that have a text
        text = msg.get("text", "")
        # Find all user mentions in this message.
        matches = tag_pattern.findall(text)
        for user_id in matches:
            tag_count[user_id] = tag_count.get(user_id, 0) + 1

    # Get channel members.
    members = get_channel_members(CHANNEL_ID)
    print(f"Found {len(members)} members in channel {CHANNEL_ID}.")

    # Get mapping of all users (id -> display name)
    # user_info = get_all_users()
    # Instead of bulk downloading all users, we lookup each member individually.
    member_names = {}
    for user_id in members:
        name = get_user_name(user_id)
        if name is not None:
            member_names[user_id] = name
        else:
            # In case the user is deleted or a bot, fallback to the user ID.
            member_names[user_id] = user_id

    # Create a list of members not tagged at all.
    #    not_tagged = []
    #    for member_id in members:
    #        if tag_count.get(member_id, 0) == 0:
    #            not_tagged.append(user_info.get(member_id, member_id))  # fallback to id if name not found

    not_tagged = [member_names.get(user_id, user_id) for user_id in members if tag_count.get(user_id, 0) == 0]

    # Sort tag_count items for the three most tagged.
    sorted_tags = sorted(tag_count.items(), key=lambda x: x[1], reverse=True)
    top_three = sorted_tags[:3]
    # Convert user ids to names for the top three.
    #    top_three_list = [(user_info.get(user_id, user_id), count) for user_id, count in top_three]
    top_three_list = [(member_names.get(user_id, user_id), count) for user_id, count in top_three]

    print("\nTop Three Most Tagged Members in the Last 30 Days:")
    if top_three_list:
        for name, count in top_three_list:
            print(f"  {name}: mentioned {count} time(s)")
    else:
        print("  No tags found.")

    print("\nMembers who were not tagged at all in the last 30 days:")
    if not_tagged:
        for name in not_tagged:
            print(f"  {name}")
    else:
        print("  Everyone was tagged at least once.")


if __name__ == "main":
    main()
else:
    main()
