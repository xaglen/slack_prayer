# slack-prayer
This script encourages people to pray for specific people using Biblical prayers as a springboard. No effort is made to prevent back-to-back duplication of prayer recipients or of Bible prayers.

# Usage
1) `pip install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib`
2) Create a Google Sheet with at least three colunms: first name, last name, Slack ID
3) Create credentials for a [Google Service Account](https://developers.google.com/workspace/guides/create-credentials) (you need to generate a `credentials.json` file)
4) Copy `settings.example.py` to `settings.py` and fill in the correct data for your account.
5) Set up a cron job to run the script. This is the cron I use: `2 10 * * * /usr/bin/python3 /PATH/TO/pray/slack.py > /dev/null 2>&1` - this runs the scripts at 10:02am every day.
