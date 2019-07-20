Generate RSS2 Feeds from Eventbrite API
=======================================

Using the Eventbrite API, generate RSS feeds (and maybe other things,
someday).

This project is similar to
[google-calendar-helpers](https://github.com/pnijjar/google-calendar-helpers)
except there is no testing. 

At some point these projects should be merged.

Deployment
----------

- Generate an Eventbrite API key: <https://eventbriteapi.com> . If you
  have ever made an Eventbrite account as an event attendee you can
  use the same login to get a key here. You only need the "Anonymous
  access OAuth Token".
- In order to validate the RSS feeds, `lxml` is required, but this
  depends on the `libxml2-dev` and `libxslt1-dev` packages. So install
  them: `apt install libxml2-dev libxslt1-dev build-essential`.
- Use `virtualenv` to set up a Python 3 environment: `virtualenv -p
  /usr/bin/python3 venv`
- Activate the environment: `source venv/bin/activate`
- Install dependencies: `pip install -r requirements.txt`
- Copy `config.py.example` to `config-demo.py` and customize it to your
  needs.
- Run `gen_rss_eventbrite.py --config config-demo.py`


Caveats
-------

- `config.py` is sourced by the script and is dangerous!
- It does not appear that you can protect this API key by IP address
  or anything.
