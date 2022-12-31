Generate RSS2 Feeds from Eventbrite API
=======================================

Using the Eventbrite API, generate RSS/iCal feeds (and maybe other things,
someday).

Since the Eventbrite Search API was shut down in December 2019, the
script fetches event IDs from Eventbrite's HTML events listings. 
It then uses the API to grab event details. As of this writing, it
costs two API calls to retrieve information for one event, so the
script attempts to minimize the number of API calls per run.

The script can handle "Things to do" pages (eg
`https://www.eventbrite.ca/d/canada--waterloo--10327/all-events/`) and
organizer-specific page (eg
`https://www.eventbrite.com/o/faithtech-11613235556`). Maybe it can
handle other pages as well. 

This project is similar to
[google-calendar-helpers](https://github.com/pnijjar/google-calendar-helpers)
except there is no testing. 

At some point these projects should be merged or a library of common
functions should be factored out. 

Deployment
----------

- Generate an Eventbrite API key: <https://eventbriteapi.com> . If you
  have ever made an Eventbrite account as an event attendee you can
  use the same login to get a key here. You only need the "Anonymous
  access OAuth Token".
- Use `virtualenv` to set up a Python 3 environment: `virtualenv -p
  /usr/bin/python3 venv`
- Activate the environment: `source venv/bin/activate`
- Install dependencies: `pip install -r requirements.txt`
- Copy `config.yaml.example` to `config-demo.yaml` and customize it to your
  needs.
- Run `gen_rss_eventbrite.py --config config-demo.yaml`
  or `gen_ical_eventbrite.py --config config-demo.yaml` 
  or `gen_rss_ical_eventbrite.py --config config-demo.yaml` 


Caveats
-------

- It does not appear that you can protect this API key by IP address
  or anything. Try hard not to check it into a public Git repo. 
