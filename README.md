# slack-prayer
This script encourages people to pray for specific people using Biblical prayers as a springboard. By design no effort is made to prevent back-to-back duplication of prayer recipients - if someone gets selected two or three days in a row we just assume they need extra prayer. The prayers are cycled through in order, each day advancing to a new passage.

# Usage
1) `pip install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib`
2) Create a Google Sheet with at least three columns: first name, last name, Slack ID
3) Create credentials for a [Google Service Account](https://developers.google.com/workspace/guides/create-credentials) with access to the spreadsheet. You need to generate a `credentials.json` file for the script to access the Google Sheet on your behalf.
4) Copy `settings.example.py` to `settings.py` and fill in the correct data for your account.
5) Set up a cron job to run the script. This is the cron I use: `2 10 * * * /usr/bin/python3 /PATH/TO/pray/slack.py > /dev/null 2>&1` - this runs the scripts at 10:02am every day.

# Customization
It would be easy to modify this script to pull from everyone who is part of a given Slack channel using [conversations.members](https://api.slack.com/methods/conversations.members). The current script doesn't do it because we're praying for formal members of a specific organization.

# A Potential Gotcha
google-api-python-client 1.5.3 requires oauth2client<4.0.0,>=1.5.0, so if you have an incomotabile version of oauth2client already installed you might receive `AttributeError: 'Credentials' object has no attribute 'authorize'` and it is super annoying to debug. If that happens, either set this up in a virtual environment and run only what you need, or `pip uninstall oauth2client google-api-python-client` and then `pip install google-api-python-client` (it will automatically install the correct dependency)
