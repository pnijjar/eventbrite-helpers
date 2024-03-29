#!/usr/bin/env python3

import os

# The EventBrite API token we need
# The anonymous access token is fine. 
API_TOKEN = "YOURTOKENHERE"

# Deprecated
# QUERY_ARGS
# QUERY_EVENTS_CHANGED
# SPLIT_DESCRIPTION_API


# Used as the link field in the RSS feed
WEBSITE='http://eventbrite.ca'

# Give this feed a common basename
FEED_BASENAME="eventbrite_kitchener"

# Used as the location of this feed
FEED_LINK="{}/{}.rss".format(WEBSITE, FEED_BASENAME,)

FEED_TITLE="Eventbrite: Waterloo Region Firehose"
FEED_DESCRIPTION="All Events within 15km of Kitchener"

# Where to save the output, and what to call it
SRCDIR=os.path.abspath(os.path.dirname(__file__))


# NEW: There are now three RSS feeds:
# - OUTRSS: live events not excluded
# - OUTRSS_FILTERED: live events in a filtered list
# - OUTRSS_VIRTUAL: virtual events that somehow ended up in the feed
OUTRSS=os.path.join(SRCDIR, "output", "{}.rss".format(FEED_BASENAME,))
OUTRSS_FILTERED=os.path.join(SRCDIR, "output", "{}-filt.rss".format(
  FEED_BASENAME,))
OUTRSS_VIRTUAL=os.path.join(SRCDIR, "output", "{}-virt.rss".format(
  FEED_BASENAME,))

# Same for ical feeds
OUTICAL=os.path.join(SRCDIR, "output", "{}.ics".format(FEED_BASENAME,))
OUTICAL_FILTERED=os.path.join(SRCDIR, "output", "{}-filt.ics".format(
  FEED_BASENAME,))
OUTICAL_VIRTUAL=os.path.join(SRCDIR, "output", "{}-virt.ics".format(
  FEED_BASENAME,))


# This is the raw JSON we collect
OUTJSON=os.path.join(SRCDIR, "output", "{}.json".format(FEED_BASENAME,))

# This is processed JSON
OUT_EVENT_DICT=os.path.join(
  SRCDIR,
  "output",
  "{}-events-processed.json".format(FEED_BASENAME,))

# Where to log events
LOGFILE=os.path.join(SRCDIR, "logs", "eventbrite.log")

# How verbose should logging be to the file and to the
# screen (display)?
# Call the function with --help to see the allowed values.
LOGLEVEL_FILE='info'
LOGLEVEL_SCREEN='error'
LOGLEVEL_DISPLAY='error'

# Who is responsible for this feed
WEBMASTER="admin@example.com"
WEBMASTER_NAME="Webmaster"

# What is the filesystem path to the templates?
# (Same folder as config.py?)
TEMPLATE_DIR=SRCDIR

# For datetime nonsense
TIMEZONE="America/Toronto"


# Do we attempt to get full descriptions from the
# /events/(event_id)/description endpoint? 
# This costs one API call PER EVENT, and you get 1000 events/hour
GET_FULL_DESCRIPTIONS=True


# What is the currency used in this application? I guess you are in 
# trouble if there are multiple currencies. You can probably be more
# sophisticated by translating the currency code (eg "CAN") to a
# symbol, but this is good enough for me. 
CURRENCY_SYMBOL='$'


# In what geographic rectangle must events be to count as "local"?
# This is pretty ad-hoc, because most regions (not even
# Saskatchewan!) are actually rectangular. But this is a rough bound 
# so that events from far away will not be included. 
GEO_BOUNDARY = { 
  'lat_max': 43.689111,
  'lat_min': 43.266807,
  'long_max': -80.189287,
  'long_min': -80.869031,
  }

# Collection of Eventbrite "tagged" URLs. Look for events here. 
# These can be organizers or "Stuff to do in X" URLs (but use 
# the 'all-events/' version)
EVENTBRITE_TARGET_URLS = [ 
  'https://www.eventbrite.ca/d/canada--waterloo--10327/all-events/',
  'https://www.eventbrite.com/o/the-new-republic-31358633543',
  ]

# There can be many pages of results. How many should we get?
# As we go down the pages events tend to get further away.
# This is per entry on EVENTBRITE_TARGET_URLS. Set to a big number
# to get everything, but keep in mind that every new event costs 2 API
# calls, and this is per URL, not overall (sorry).
MAX_EVENTBRITE_PAGES_TO_FETCH = 10


# list of organizer_id fields to filter.
# These organizers flood Eventbrite with events that are not
# personally relevent, and so get a different feed.
FILTERED_ORGANIZERS = [
  "6827056193", # Manhattan Young Democrats
]
