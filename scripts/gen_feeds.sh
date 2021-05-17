#!/bin/bash 

# $1 is the virtualenv path
# $2 is the path to the script
# $3 is the config file
# https://stackoverflow.com/questions/4150671

source $1/bin/activate
# Yikes.
cd $2
python gen_rss_ical_eventbrite.py --config $3

