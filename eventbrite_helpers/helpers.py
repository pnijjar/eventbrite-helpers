#!/usr/bin/env python3

import argparse, sys, os
import json
import requests
import jinja2
import pytz, datetime, dateutil.parser
import re
import logging, logging.handlers
import pprint
from bs4 import BeautifulSoup

RSS_TEMPLATE="rss_template_eventbrite.jinja2"
ICAL_TEMPLATE="ical_template_eventbrite.jinja2"

# Order is important! More verbose is earlier.
LOGLEVELS = ['debug', 'info', 'warning', 'error', 'critical', 'silent']

# Probably these should be configurable. Oh wells.
LOGGING_MAX_LOGFILE_SIZE = 1024 * 1024
LOGGING_NUM_LOGFILES_TO_KEEP = 5

# Save each step of the operation?
DUMP=False

# See:
# https://stackoverflow.com/questions/730133/invalid-characters-in-xml
INVALID_XML_CHARS=re.compile(
  r'[^\u0009\u000a\u000d\u0020-\ud7ff\ue000-\uFFFD\u10000-\u10ffff]'
  )
INVALID_FILENAME_CHARS=re.compile(r'[/?]')

LIMIT_FETCH = False
SKIP_API = False

# 406: not acceptable (you is blocked)
# 429: past rate limit (ugh)
EVENTBRITE_LIMIT_STATUSES = [406, 429,]


_num_api_calls = 0

# ---- EXCEPTIONS -----
class NoEventbriteIDException(Exception):
    pass

class UnknownHandlerException(Exception):
    pass

# ------------------------------
def print_from_template (s): 
    """ Show the value of a string that is being processed in a 
        Jinja template, for debugging.
    """
    print(s)
    return s

# ------------------------------
def clean_eventbrite_url (url):
   """ Remove unneeded query info from Eventbrite URL
   """

   if url.find('?') >= 0:
       try:
           base, params = url.split("?", 1) 
       except ValueError as e:
           logging.error(
             "Could not split." 
             "Offending url is {}".format(url))
           return url

       return base

   return url


# -----------------------------
def url_to_id(url):
    """ Convert URL to ID, using regular expressions. Now I have two
    problems. The assumption is that the final number of an URL is the 
    ID. eg 
    https://www.eventbrite.ca/e/sunday-afternoon-service-tickets-142594456859
    produces
    142594456859

    Another possibility is the format 
    https://eventbrite.ca/e/142594456859
    """
     
    # .+ : https://www.eventbrite.ca
    # /e/ : /e/ literally
    # (?:.+-)? : Possibly 'sunday-afternoon-service-tickets-' . 
    #   '?:' means "group but do not count as a matching group"
    # (\d+)$ : end should be just digits. Match as group(1)
    id_regex = re.compile(r'.+/e/(?:.+-)?(\d+)$')
    try:
        id = re.match(id_regex, url).group(1)
    except AttributeError:
        logging.error("No ID in URL {}".format(url))
        raise NoEventbriteIDException("No ID in URL {}".format(url))

    return id

# -----------------------------
def url_to_filename(url):
    """ Convert url to a string that can be a filename. Slashes are
        bad. Periods are okay? Query strings are bad?
    """

    return re.sub(INVALID_FILENAME_CHARS, "_", url)



# -----------------------------
def event_is_virtual(event):
    """ Determine if event is virtual. Produces a boolean."""

    return 'location' in event and \
      '@type' in event['location'] and \
      event['location']['@type'] == "VirtualLocation"

# -----------------------------
def event_in_boundary(event):
    """ Determine whether an event is in the range. Depends on 
        global constant.
        Does not handle weird GMT boundaries.
        Says that virtual events are false.

        Consumes an event (with no ID)
        Prereq: event is not virtual. 

        Produces a boolean
    """

    id = url_to_id(event['url'])

    if not 'location' in event:
        logging.debug("{}: no location field!".format(id))
        return False

    elif not 'geo' in event['location']:
        logging.debug("{}: no lat/long location!".format(id))
        return False

    else:
        geo = event['location']['geo']
        
        if float(geo['latitude']) >= config.GEO_BOUNDARY['lat_min'] \
          and float(geo['latitude']) <= config.GEO_BOUNDARY['lat_max'] \
          and float(geo['longitude']) >= config.GEO_BOUNDARY['long_min'] \
          and float(geo['longitude']) <= config.GEO_BOUNDARY['long_max']:

            return True
        else:
            logging.debug("{}: Not in boundary!".format(id))
            #print(event['name'])
            #pprint.pprint(event['location'])
            return False


# ------------------------------
def get_rfc822_datestring (google_date): 
    """ Convert whatever date Google is using to the RFC-822 dates
        that RSS wants.
    """

    # Sometimes dates look like "0000-12-29T00:00.000Z" and this
    # confuses the date parser...
    d = dateutil.parser.parse(google_date)

    # Output the proper format
    return d.strftime("%a, %d %b %Y %T %z")

# ------------------------------
def get_ical_datetime (local_date):
    """ Convert some date (not necessarily from Google, but whatever)
        to a format that iCal feeds want. 2019-03-03 04:23 becomes
        20190303T042300 . This is LOCAL DATE.
    """

    d = dateutil.parser.parse(local_date)

    return d.strftime("%Y%m%dT%H%M00")


# ------------------------------
def get_ical_datetime_utc (local_date):
    """ Convert some date (not necessarily from Google, but whatever)
        to a format that iCal feeds want. 2019-03-03 04:23 becomes
        20190303T042300 . This is UTC date.
    """

    d = dateutil.parser.parse(local_date)
    d_utc = d.astimezone(pytz.timezone('UTC'))

    return d_utc.strftime("%Y%m%dT%H%M00Z")


# -------------------------------
def datetime_to_utc_string (d):
    """ Unlike everything else, take a DATETIME and produce
        a string representing the datetime as UTC.
    """

    d_utc = d.astimezone(pytz.timezone('UTC'))
    return d_utc.strftime("%FT%H:%M:%SZ")



# ------------------------------
def get_iso8601_datetime (google_date):
    """ Convert a date to something that is easy to copy 
        and paste: 2019-03-03 04:34
    """
    d = dateutil.parser.parse(google_date)

    # 2005-10-02 20:00
    return d.strftime("%F %H:%M")

# ------------------------------
def get_human_datestring (google_date): 
    """ RFC 822 is ugly for humans. Use something nicer. """

    d = dateutil.parser.parse(google_date)
    
    # Wednesday, Oct 02 2005, 8:00pm
    return d.strftime("%A, %b %d %Y, %l:%M%P")

# ------------------------------
def get_human_dateonly (google_date):
    """ If there is no minute defined then the date looks bad.
    """

    d = dateutil.parser.parse(google_date)
    
    # Wednesday, Oct 02 2005
    return d.strftime("%A, %b %d %Y")

# ------------------------------
def get_short_human_dateonly (google_date):
    """ Readable by humans, but shorter. """

    d = dateutil.parser.parse(google_date)

    # Sun, Feb 18
    return d.strftime("%a, %b %e")

# ------------------------------
def get_short_human_datetime (google_date):
    """ Date time readable by humans, but shorter. """

    d = dateutil.parser.parse(google_date)

    # Sun, Feb 18, 8:00pm
    return d.strftime("%a, %b %e, %l:%M%P")


# ------------------------------
def get_human_timeonly (google_date):
    """ Forget the date. Just gimme the time"""

    d = dateutil.parser.parse(google_date)
    #  8:00pm
    return d.strftime("%l:%M%P")

# -------------------------------
def get_duration_in_minutes(end_date, start_date):
    """ Compute the difference of two days in minutes.
        Call this on the end.
    """

    d_end = dateutil.parser.parse(end_date)
    d_start = dateutil.parser.parse(start_date)

    diff = d_end - d_start
    one_minute = datetime.timedelta(minutes=1)

    return diff // one_minute

# ------------------------------
def get_time_now():
   
    target_timezone = pytz.timezone(config.TIMEZONE)
    time_now = datetime.datetime.now(tz=target_timezone)

    return time_now


# ------------------------------
def remove_invalid_xml_chars (victim):
    """ Some control characters are prohibited in XML. Delete them.
    """
    
    if not victim:
        return ""

    return re.sub(INVALID_XML_CHARS, "", victim)


# ------------------------------
def ical_escape (victim):
    """ iCal has weird escaping rules. Implement them.
        iCal also has weird block formatting rules. Ugh.
    """
    
    if not victim:
        return "EMPTY STRING PROVIDED TO ICAL_ESCAPE"
    
    # https://stackoverflow.com/questions/18935754/how-to-escape-special-characters-of-a-string-with-single-backslashes
    return victim.translate(
      str.maketrans({
        "," : r"\,",
        ";" : r"\;",
        "\\": r"\\",
        "\n": r"\n",
        "\r": r"",
        }))


# ------------------------------
def get_ical_block(text, prefix=""):
    """ Use the weird iCal folding rules to break a big block of
        text into escaped iCal format.

        prefix is an optional prefix to take into consideration
        when constructing the string (eg "DESCRIPTION:"). The 
        prefix is NOT produced in the filter.
        The length of the prefix should be shorter than the length 
        of an iCalendar line (currently set to 74)
    """

    # Specified in https://tools.ietf.org/html/rfc5545#section-3.1
    # This should not be bigger than 75.
    MAX_LINE_LEN = 73

    escaped_text = ical_escape(text)

    # You had better hope that the length of the prefix is less than 
    # the length of a line. 
    tot_len = len(escaped_text) + len(prefix)

    retval = ""
    
    line_no = 0
    pos = 0

    # There might be an off-by-one here but I think it does not
    # matter. 
    while (line_no * MAX_LINE_LEN) < tot_len:
        if line_no == 0:
            delta = MAX_LINE_LEN - len(prefix)
            retval += escaped_text[0:delta]
            pos += delta
        else:
            # Prefix with space
            retval += "\n "
            retval += escaped_text[pos:(pos + MAX_LINE_LEN)]
            pos += MAX_LINE_LEN
        
        line_no += 1

    return retval

# ------------------------------
""" This calls the Eventbrite search API. May return an error 
    that we ought to handle, but don't.
"""
def call_events_api():
    global _num_api_calls

    BASE_URL = "https://www.eventbriteapi.com/v3"

    search_api_url = "{}/events/search/".format(
      BASE_URL,
      )

    curr_page = 1
    more_items = True

    query_args = config.QUERY_ARGS

    if config.QUERY_EVENTS_CHANGED_DAYS: 
        since = datetime.timedelta(days=config.QUERY_EVENTS_CHANGED_DAYS)
        # Make a query relative to now, minus the delta.
        now = get_time_now()
        cutoff = now - since
        
        query_args['date_modified.range_start'] = datetime_to_utc_string(cutoff)


    event_list = []


    while more_items: 
        api_params = { 
          'token': config.API_TOKEN,
          'page' : curr_page,
          'expand' : 'venue,ticket_availability,description',
          }

        api_params.update(query_args)

        r = requests.get(search_api_url, api_params)

        if r.status_code in EVENTBRITE_LIMIT_STATUSES:
            more_items = False
            logging.warn("Received status code {} "
                  "after fetching {} events with {} "
                  "API calls".format(
                    r.status_code,
                    len(event_list),
                    _num_api_calls))
            break

        r.raise_for_status()
        _num_api_calls = _num_api_calls + 1
        r_json = r.json() 

        event_list = event_list + r_json['events']

        if 'error' in r_json.keys():
            more_items = False
        elif 'pagination' in r_json.keys() \
          and r_json['pagination']['has_more_items'] :
            curr_page = curr_page + 1

            if LIMIT_FETCH:
                more_items = False
            else:
                more_items = True
        else:
            more_items = False

        #print("Processed page {}".format(curr_page,))


    #print("Number of events: {}\n\n".format(len(event_list)))

    # Maybe this sort criterion should be a config?
    event_list.sort(key=lambda x: x['created'], reverse=True)


    # Current as of API 3.7.0: the 'description' field is not actually
    # the description any more. Instead you need to call another
    # endpoint to get this information. You can batch these requests
    # but the responses don't contain the original IDs! So
    # frustrating. 

    # The easy way to deal with this is to get the full description 
    # for EVERYTHING, since everything will eventually migrate to the 
    # new API. 
    if config.GET_FULL_DESCRIPTIONS:
        desc_ids = [] 
        desc_params = []
        for event in event_list:
            if event['version'] >= config.SPLIT_DESCRIPTION_API: 
                desc_ids.append(event['id'])
                desc_params.append({
                  'method': 'GET',
                  'relative_url': "events/{}/description".format(
                                     event['id'],
                                     )
                  })
            else:
                # This feels gross. 
                event['full_description'] = event['description']['html']
        
        if desc_ids:
            num_events = len(event_list)
            #print("Got {} IDs".format(len(desc_ids)))
            desc_api_params = {
              'token': config.API_TOKEN,
              }

            batch_params = {
              'batch': json.dumps(desc_params)
              }

            rd = requests.post(
              "{}/batch/".format(BASE_URL,),
              params=desc_api_params,
              data=batch_params,
              )
            
            # Throw an error if something went bad
            rd.raise_for_status()

            event_index = 0

            for (id,resp) in zip(desc_ids,rd.json()):
                # This is gross too. Let's hope that my calculations
                # are correct and the event list does not get out of 
                # order.
                while event_list[event_index]['id'] != id:
                    event_index = event_index + 1

                if resp['code'] == 200:
                    new_desc = json.loads(resp['body'])
                    event_list[event_index]['full_description'] = \
                      new_desc['description']
                    # print("Set desc for id {}".format(id))

    return event_list

# -----------------------------
def call_api(api_url, api_params):
    """ Call the Eventbrite API and produce the JSON, or an exception.
    """
    global _num_api_calls

    r = requests.get(api_url, api_params)

    _num_api_calls = _num_api_calls + 1

    if r.status_code in EVENTBRITE_LIMIT_STATUSES:
        logging.warn("Received status code {} "
          "after {} API calls this run".format(
          r.status_code,
          _num_api_calls
          ))

    r.raise_for_status()


    return r.json() 



# ------------------------------
def get_event_from_api(id):
    """ This calls the Eventbrite event API. May return an error 
        that we ought to handle, but don't.

        id: The ID of the event to get
    """

    BASE_URL = "https://www.eventbriteapi.com/v3"

    event_api_url = "{}/events/{}".format(
      BASE_URL,
      id,
      )

    desc_api_url = "{}/events/{}/description".format(
      BASE_URL,
      id,
      )

    event_api_params = { 
      'token': config.API_TOKEN,
      'expand' : \
        'venue,organizer,ticket_availability',
      }

    desc_api_params = { 
      'token': config.API_TOKEN,
       }


    try:
        event = call_api(event_api_url, event_api_params)

        # TODO: Get rid of this option?
        if config.GET_FULL_DESCRIPTIONS:
            desc = call_api(desc_api_url, desc_api_params)
            event['full_description'] = desc['description']
    
    except requests.exceptions.HTTPError as e:
        # Failed. Now what?
        # The description may or may not be present. Ugh.
        logging.error("get_event_from_api: Received API error: {}".format(e))
        return None

    return event


# -----------------------------
def print_json(j):
    """ Print JSON nicely, because debugging is frustrating.
    """
    print(json.dumps(j, indent=2, separators=(',', ': ')))



# ------------------------------
def generate_ical(cal_dict, feed_title):
    """ Generate an iCal feed given a JSON file.
    """

    # --- Process template 

    template_loader = jinja2.FileSystemLoader(
        searchpath=config.TEMPLATE_DIR
        )
    template_env = jinja2.Environment( 
        loader=template_loader,
        autoescape=False,
        )
    template_env.filters['print'] = print_from_template
    template_env.filters['cleanurl'] = clean_eventbrite_url
    template_env.filters['ical_block'] = get_ical_block
    template_env.filters['ical_datetime'] = get_ical_datetime
    template_env.filters['ical_datetime_utc'] = get_ical_datetime_utc
    template_env.filters['ical_escape'] = ical_escape

    time_now = get_time_now()
    time_now_formatted = time_now.strftime("%a, %d %b %Y %T %z")

    # Remove http:// or https:// from the website.
    # This produces a LIST, and we take the final part.
    bare_website = config.WEBSITE.split("//")[-1]

    template = template_env.get_template( ICAL_TEMPLATE ) 
    template_vars = { 
      "feed_title": feed_title,
      "feed_description": config.FEED_DESCRIPTION,
      "feed_webmaster" : config.WEBMASTER,
      "feed_webmaster_name" : config.WEBMASTER_NAME,
      "feed_builddate" : time_now_formatted,
      "feed_pubdate" : time_now_formatted,
      "feed_website" : bare_website,
      "feed_items" : cal_dict,
      "feed_selflink" : config.FEED_LINK,
      "feed_currency" : config.CURRENCY_SYMBOL,
      "feed_full_descriptions" : config.GET_FULL_DESCRIPTIONS,
      "feed_timezone" : config.TIMEZONE,
      }

    output_ical = template.render(template_vars)

    return output_ical


# ------------------------------
def generate_rss(cal_dict, feed_title):
    """ Given a JSON formatted calendar dictionary, make and return 
        the RSS file.
    """

    # --- Process template 

    template_loader = jinja2.FileSystemLoader(
        searchpath=config.TEMPLATE_DIR
        )
    template_env = jinja2.Environment( 
        loader=template_loader,
        autoescape=True,
        )
    template_env.filters['rfc822'] = get_rfc822_datestring
    template_env.filters['humandate'] = get_human_datestring
    template_env.filters['humandateonly'] = get_human_dateonly
    template_env.filters['iso8601'] = get_iso8601_datetime 
    template_env.filters['print'] = print_from_template
    template_env.filters['cleanurl'] = clean_eventbrite_url
    template_env.filters['cleanxml'] = remove_invalid_xml_chars
    template_env.filters['minutes_since'] = get_duration_in_minutes


    time_now = get_time_now()
    time_now_formatted = time_now.strftime("%a, %d %b %Y %T %z")

    template = template_env.get_template( RSS_TEMPLATE ) 
    template_vars = { 
      "feed_title": feed_title,
      "feed_description": config.FEED_DESCRIPTION,
      "feed_webmaster" : config.WEBMASTER,
      "feed_webmaster_name" : config.WEBMASTER_NAME,
      "feed_builddate" : time_now_formatted,
      "feed_pubdate" : time_now_formatted,
      "feed_website" : config.WEBSITE,
      #"feed_logo_url" : config.LOGO,
      "feed_items" : cal_dict,
      "feed_selflink" : config.FEED_LINK,
      "feed_currency" : config.CURRENCY_SYMBOL,
      "feed_full_descriptions" : config.GET_FULL_DESCRIPTIONS,
      }

    output_rss = template.render(template_vars)

    return str(output_rss)

## ------------------------------
def print_results(events):
    for event in events:
        #print("{}\\n\n".format(event))
        print("{}\n{}\n{}\nCreated: {}\n\n".format(
          event['name']['text'],
          event['venue']['address']['localized_address_display'],
          event['url'],
          event['created']
          ))



## ------------------------------
def loglevel_str_to_const(loglevel_str):
    """ Consumes an element of LOGLEVELS and produces the 
        corresponding logging constant.

        Pre: loglevel_str is in LOGLEVELS?
    """

    loglevel = None

    if loglevel_str == 'debug':
        loglevel = logging.DEBUG
    elif loglevel_str == 'error':
        loglevel = logging.ERROR
    elif loglevel_str == 'warning':
        loglevel = logging.WARNING
    elif loglevel_str == 'critical':
        loglevel = logging.CRITICAL
    elif loglevel_str == 'info':
        loglevel = logging.INFO
    elif loglevel_str == 'silent':
        loglevel = 1000

    return loglevel

## -----------------------------
def config_logging(config, args):
    """ Set up logging given the config and args.
    """
    formatter = logging.Formatter(
      fmt='%(asctime)s %(levelname)s: %(message)s',
      datefmt='%Y-%m-%d %H:%M {}'.format(args.configfile),
      )

    logger = logging.getLogger() # eventbrite_helpers
    logger.setLevel(logging.DEBUG)

    #root_logger = logging.getLogger()
    #root_logger.setLevel(logging.DEBUG)

    loglevel_file = 'silent'
    if args.verbose:
        loglevel_file = 'debug'
    elif args.loglevel_file:
        loglevel_file = args.loglevel_file
    else:
        # Better hope this is defined!
        loglevel_file = config.LOGLEVEL_FILE

    if loglevel_file != 'silent':
        loghandler = logging.handlers.RotatingFileHandler(
          filename=config.LOGFILE,
          maxBytes=LOGGING_MAX_LOGFILE_SIZE,
          backupCount=LOGGING_NUM_LOGFILES_TO_KEEP,
          )

        # Could factor out these lines into a new helper
        loghandler.setLevel(loglevel_str_to_const(loglevel_file))
        loghandler.setFormatter(formatter)
        logger.addHandler(loghandler)


    loglevel_display = 'silent'
    if args.verbose:
        loglevel_display = 'debug'
    elif args.loglevel_display:
        loglevel_display = args.loglevel_display
    else:
        loglevel_display = config.LOGLEVEL_DISPLAY

    if loglevel_display != 'silent':
        loghandler_display = logging.StreamHandler()
        loghandler_display.setLevel(
          loglevel_str_to_const(loglevel_display)
          )
        loghandler_display.setFormatter(formatter)
        logger.addHandler(loghandler_display)


    # Ugh. Stupid requests is doing the wrong thing.
    #quietest_level = max(
    #    loglevel_str_to_const(loglevel_display),
    #    loglevel_str_to_const(loglevel_file)
    #    )


    #root_logger = logging.getLogger("root")
    #root_logger.setLevel(quietest_level)

    #req_logger = logging.getLogger("requests")
    #req_logger.setLevel(quietest_level)

    #urllib_logger = logging.getLogger("urllib3")
    #urllib_logger.setLevel(quietest_level)


    #for key in logging.Logger.manager.loggerDict:
        #logging.getLogger(key).setLevel(quietest_level)
        # print(key)
        #pass

    logging.debug("Display loglevel: {} ({}), File loglevel: {} ({})".format(
      loglevel_display,
      loglevel_str_to_const(loglevel_display),
      loglevel_file,
      loglevel_str_to_const(loglevel_file),
      ))


## ------------------------------
def load_config(configfile=None):
    """ Load configuration definitions.
       (This is really scary, actually. We are trusting that the 
       config.py we are taking as input is sane!) 

       If both the commandline and the parameter are 
       specified then the commandline takes precedence.
    """

    # '/home/pnijjar/watcamp/python_rss/gcal_helpers/config.py'
    # See: http://www.karoltomala.com/blog/?p=622
    DEFAULT_CONFIG_SOURCEFILE = os.path.join(
        os.getcwd(),
        'config.py',
        )

    config_location=None


    # Now parse commandline options (Here??? This code smells bad.)
    parser = argparse.ArgumentParser(
        description="Generate RSS (and maybe other things)"
            " from Eventbrite listings",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        )
    parser.add_argument('-c', '--configfile', 
        help='configuration file location',
        default=DEFAULT_CONFIG_SOURCEFILE,
        )
    parser.add_argument('-s', '--small',
        help='small: retrieve fewer entries',
        action='store_true',
        )
    parser.add_argument('--skip-api',
        help='do not call online API -- use cached data only',
        action='store_true',
        )
    parser.add_argument('-v', '--verbose',
        help='print debug info to log and stdout',
        action='store_true',
        )
    parser.add_argument('-lf', '--loglevel-file',
        help='Log level messages to print to the file.',
        choices=LOGLEVELS,
        )
    parser.add_argument('-ld', '--loglevel-display',
        help='Log level messages to print to the display.',
        choices=LOGLEVELS,
        )
    parser.add_argument('--dump-dir',
        help='Dump intermediate results in this folder',
        )

    args = parser.parse_args()

    if configfile:
        config_location=configfile
    elif args.configfile: # Ugh. Default value will take precedence.
        config_location = os.path.abspath(args.configfile)
    else: 
        config_location = DEFAULT_CONFIG_SOURCEFILE

    # http://stackoverflow.com/questions/11990556/python-how-to-make-global
    global config

    # Blargh. You can load modules from paths, but the syntax is
    # different depending on the version of python. 
    # http://stackoverflow.com/questions/67631/how-to-import-a-mod
    # https://stackoverflow.com/questions/1093322/how-do-i-ch

    if sys.version_info >= (3,5): 
        import importlib.util 
        spec = importlib.util.spec_from_file_location(
            'config',
            config_location,
            )
        config = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(config)
    elif sys.version_info >= (3,3):
        # This is the only one I can test. Sad!
        from importlib.machinery import SourceFileLoader
        config = SourceFileLoader( 'config', config_location,).load_module()
    else:
        import imp
        config = imp.load_source( 'config', config_location,)


    config_logging(config, args)

    if args.small:
        # Ugh. Bad code smell. Should not use globals (but config.* is
        # okay?)
        global LIMIT_FETCH
        LIMIT_FETCH = True
    
    if args.skip_api:
        global SKIP_API
        SKIP_API = True

    if args.dump_dir:
        global DUMP
        DUMP = True
        config.dump_dir = args.dump_dir

        # Check if folder exists. If not, create it. 
        if os.path.exists(args.dump_dir) and \
          not os.path.isdir(args.dump_dir):
            logging.warning(
              "Uh oh. {} exists but is not a dir. Not dumping.".format(
                args.dump_dir))
            DUMP = False
        elif not os.path.isdir(args.dump_dir):
            logging.info("{} does not exist. Creating".format(
              args.dump_dir))
            os.makedirs(args.dump_dir)
        else:
            logging.debug("{} exists. Reusing!".format(
              args.dump_dir))


    # For test harness
    return config
# ------------------------------
def sort_json_events(events):
    """ Given a list of Eventbrite events, sort them in 
        descending order by ID and produce the result.
    """

    sorted_events = sorted(
      events, 
      key=lambda item: item['id'],
      reverse=True,
      )
    return sorted_events
       

# -----------------------------
def sort_json_events_by_pubdate(events):
    """ Given a list of Eventbrite events, sort them in 
        descending order by published date and produce the result.
    """

    sorted_events = sorted(
      events,
      key=lambda item: item['published'],
      reverse=True,
      )

    return sorted_events
            
# ------------------------------
def merge_and_prune(old_items, update_items):
    """ Given a list of previously_processed events and new 
        events, produce a merge of the two, AND get rid of 
        any events that are stale (ie end before the 
        current time)

        Both lists must be sorted in DESCENDING order according
        to Eventbrite ID. 
    """

    too_old = get_time_now()


    # Mein Gott. Are we back in OOT?
    pos_old = 0
    pos_upd = 0
    max_old = len(old_items)
    max_upd = len(update_items)

    merged_items = []

    num_dropped = 0
    num_dups = 0

    while pos_old < max_old or pos_upd < max_upd:

        target = None
        
        if pos_old < max_old and pos_upd < max_upd:

            key_old = old_items[pos_old]['id']
            key_upd = update_items[pos_upd]['id']

            if key_old > key_upd:
                # Old is strictly bigger
                target = old_items[pos_old]
                pos_old = pos_old + 1

            elif key_old < key_upd:
                target = update_items[pos_upd]
                pos_upd = pos_upd + 1

            elif key_old == key_upd:
                # Duplicate! The update wins. Both 
                # sources get incremented.
                target = update_items[pos_upd]
                pos_old = pos_old + 1
                pos_upd = pos_upd + 1
                num_dups = num_dups + 1

            else:
                raise AssertionError("keys don't compare")

        elif pos_old < max_old:
            # Update is done. Process old items only.
            target = old_items[pos_old]
            pos_old = pos_old + 1

        elif pos_upd < max_upd:
            target = update_items[pos_upd]
            pos_upd = pos_upd + 1

        else:
           raise AssertionError(
             "Both lists are finished but should not be!"
             )

        if dateutil.parser.parse(target['end']['utc']) >= too_old:
            merged_items.append(target)
        else:
            num_dropped = num_dropped + 1

    logging.info(
      "After merge: num_old = {}, num_updated = {}, "
      "num_dups = {}, num_dropped = {}, "
      "num_in_merge = {}".format(
        max_old,
        max_upd,
        num_dups,
        num_dropped,
        len(merged_items)
      ))

    return merged_items



# ------
def extract_events(page):
    """ Parse json events from requested page
    
    page: a BeautifulSoup object

    returns: a list?
    """
    event_script = page.find_all(type="application/ld+json")

    num_candidates = len(event_script)
    if num_candidates != 1:
        logging.debug( "Uh oh. Looked for JSON and"
          " found {} possible elements.".format(num_candidates))

    best_candidate = None

    for candidate in event_script:
        can_json = json.loads(candidate.string)

        # Events must be in a list
        if isinstance(can_json, list) and \
          len(can_json) >= 1 and \
          '@type' in can_json[0] and \
          can_json[0]['@type'] == 'Event':
            
            if best_candidate:
                logging.warn("Uh oh. There is already a candidate!"
                  "Taking latest one, I guess.")

            best_candidate = can_json
          
    if not best_candidate:
        return []
    else: 
        return best_candidate            

    
# -------
def traverse_pages(target, json_so_far, page_limit):
    """ Pull JSON from pages, to desired limit

    target : URL to fetch
    json_so_far : collected events up to this point
    page_limit: maximum pages to consume (determined by us)
    """

    if DUMP:
        htmldir = ensure_dumpdir("html-pages")
        jsondir = ensure_dumpdir("json-from-html")

    curr_page = 2
    keep_going = True
    while (curr_page <= page_limit) \
      and keep_going:
        

        payload = {'page': curr_page}
        r = requests.get(target, params=payload)

        try:
            r.raise_for_status()
            logging.debug("Fetched page {}: {}".format(curr_page, r.url))
        except requests.exceptions.HTTPError as e:
            logging.warn("Oy. Received status {} for"
              "url {} on page {}.  Bailing".format(
                r.status,
                r.url,
                curr_page,
                )) 
            return json_so_far

        page = BeautifulSoup(r.text, 'html.parser')
        new_json = extract_events(page)

        if DUMP:
            filename = url_to_filename(r.url)
            dump_file(r.text, htmldir, filename, "html")
            dump_file(new_json, jsondir, filename, "json")

        if new_json: 
            json_so_far = json_so_far + new_json

        curr_page = curr_page + 1

        if not page.find('button', { 'data-spec': 'page-next' }):
            keep_going = False

    logging.info("Traversed {} pages".format(curr_page - 1))
    
    return json_so_far

# ----------------------------
def download_events():
    """ Download events. Produces a list of JSON elements.
    """

    all_events = json.loads('[]')

    if DUMP:
        htmldir = ensure_dumpdir("html-pages")
        jsondir = ensure_dumpdir("json-from-html")

    for target in config.EVENTBRITE_TARGET_URLS:
        r = requests.get(target)
        r.raise_for_status()

        # Get the JSON I want
        page = BeautifulSoup(r.text, 'html.parser')
        

        # Update 2022-08-30: on 2022-07-27 Eventbrite changed 
        # something, and this div disappeared from the interface.

        # TODO: Put this in a try/catch block or something, in case
        # there is no such thing.
        #total_pages = 1
        #try:
        #    total_pages_div = page.find( 
        #      'div', 
        #      {'data-spec': 'paginator__last-page-link'}
        #      )
        #    total_pages = int(total_pages_div.a.contents[0])
        #    logging.info(
        #      "{}: I think there are {} pages in total".format(
        #        target,
        #        total_pages,
        #        ))
        #except Exception as e:
        #    logging.debug("No paginator found on {}".format( target))
        #    total_pages = 1

        attempt_traverse = False
        if page.find('button', { 'data-spec': 'page-next' }):
            attempt_traverse = True
            
        events = extract_events(page)

        if DUMP:
            filename = url_to_filename(target)
            dump_file(r.text, htmldir, filename, "html")
            dump_file(events, jsondir, filename, "json")

        if attempt_traverse and not LIMIT_FETCH:
            events = traverse_pages(
              target, 
              events, 
              config.MAX_EVENTBRITE_PAGES_TO_FETCH
              )
        logging.info("{}: Got {} items!".format(
          target,
          len(events))
          )

        all_events = all_events + events

    return all_events

# -----------------------------
def incorporate_events(event_dict, new_events):
    """ Incorporate new events into event_dict, if they are worthy.

        event_dict: indexed by event ID
        new_events: raw downloaded events
    """

    timezone = pytz.timezone(config.TIMEZONE)
    now = get_time_now()
    recent = now - datetime.timedelta(days=1)

    for event in new_events:
        id = url_to_id(event['url'])
        too_far = False
        filtered = False
        virtual = False

        # Make an aware date 
        end_date_raw = dateutil.parser.parse(event['endDate'])

        if end_date_raw.tzinfo is None or \
          end_date_raw.tzinfo.utcoffset(end_date_raw) is None:

            end_date = timezone.localize(end_date_raw)
        else:
            end_date = end_date_raw

        if end_date < recent:
            logging.debug("{}: ends {} and now is {}. Past?".format(
              id,
              end_date,
              recent))
            continue

        if event_is_virtual(event):
            virtual = True 
        elif not event_in_boundary(event):
            too_far = True


        if id in event_dict:
            # TODO: Compare against (short) description. 
            # If they are different then need to update. 
            #logging.debug("Event {} already in event_dict".format(id))
            continue

        if not too_far:
            api_event = get_event_from_api(id)

            if api_event is None:
                # Something went bad. Better bail 
                logging.warn("API call failed. Stopping fetch.")
                continue

            # TODO: Check against blacklist and mark as filtered
            if api_event["organizer_id"] in config.FILTERED_ORGANIZERS:
                filtered = True
        else:
            # Make a dummy event cheaply
            api_event = {}


            api_event['end'] = {
              'utc': end_date.strftime("%FT%H:%M:%SZ")
              }

        api_event['extrainfo'] = { 
          'too_far' : too_far,
          'filtered_out' : filtered,
          'virtual' : virtual,
          'added' : now.strftime("%FT%T"),
          }

        api_event['pulled_event'] = event

        event_dict[id] = api_event

# -------------------------
def prepare_event_lists(event_dict):
    """ Split event_dict into filtered and unfiltered lists of events.

        Returns a tuple:
          - non-filtered events (json)
          - filtered events (json)
          - virtual events (json)
          - list of IDs to delete from event_dict
            because they are in the past

        Filtered and non-filtered events are sorted (how?)
    """

    ids_to_delete = []
    non_filtered_events = []
    filtered_events = []
    virtual_events = []

    too_old = get_time_now() - datetime.timedelta(days=1)
    timezone = pytz.timezone(config.TIMEZONE)


    for id, event in event_dict.items():
        end_date = dateutil.parser.parse(event['end']['utc'])

        if end_date < too_old:
            ids_to_delete.append(id)
            logging.debug("Dropped event {} with end time {}".format(
              id,
              event['end']['utc']
              ))
        elif 'virtual' in event['extrainfo'] and \
          event['extrainfo']['virtual']:
            virtual_events.append(event)
        elif event['extrainfo']['too_far']:
            continue
        elif event['extrainfo']['filtered_out']:
            filtered_events.append(event)
        else:
            non_filtered_events.append(event)

        
    non_filtered_events = sort_json_events_by_pubdate(
      non_filtered_events,
      )
      
    filtered_events = sort_json_events_by_pubdate(
      filtered_events,
      )

    return non_filtered_events, filtered_events, \
      virtual_events, ids_to_delete
        


# ------------------------------
def clean_event_dict(event_dict, ids_to_delete):
    """ Removes every event with an id ids_to_delete from event_dict.
    """

    for id in ids_to_delete:
        del event_dict[id]

# ------------------------------
def ensure_dumpdir(subdir):
    """ Make sure a subfolder of config.dump_dir exists with name
        subdir. Return the full path of that folder.

        Pre: DUMP is true, and config.dump_dir is defined.
    """

    fullpath = os.path.join(config.dump_dir, subdir)

    if not os.path.isdir(fullpath):
        os.makedirs(fullpath)

    return fullpath

# -----------------------------
def dump_file(target, dumpdir, filename, file_ext):
    """ Dump a file of type file_ext to dumpdir/filename.file_ext .
        Any previously existing file will be overwritten!
    
        Pre: DUMP is true, dumpdir exists and is writeable, 
        file_ext is one of "json", "txt", "html"
    """

    dumpfile = "{}.{}".format(filename, file_ext)
    dump_path = os.path.join(dumpdir, dumpfile)

    with open(dump_path, "w", encoding='utf8') as out:
        if file_ext == "json":
            json.dump( target, out, indent=2, separators=(',', ': '))
        elif file_ext == "txt":
            pprint.pprint(target, stream=out)
        elif file_ext == "html":
            out.write(target)
        

# ------------------------------
def write_transformation(transforms):
    """ Write file(s) for the transformation. The transforms should
        be a list of strings that contain 'rss' or 'ical'.
        If I was a better programmer then I would force this.
    """

    load_config() 

    logging.info("Starting run")

    # There is a type error now.
    # old_json should be the dictionary of events.
    # It has keys that are IDs.

    # new_json is the event list. It is just a JSON list.
    # We need to compare it to elements of the event_dict. 

    # This is still sketchy, because we are still not testing for 
    # malicious input!

    if DUMP:
        ddir = config.dump_dir

    event_dict = {} 
    if os.path.isfile(config.OUT_EVENT_DICT):
        with open(config.OUT_EVENT_DICT, "r", encoding='utf8') as injson:
            event_dict = json.load(injson)

        if DUMP:
            dump_file(event_dict, ddir, "00-orig-events", 
              "json")

    if not SKIP_API: # Yay double negative
        raw_events = download_events()

        incorporate_events(event_dict, raw_events)

        if DUMP:
            dump_file(raw_events, ddir, "05-raw-events", "json")
            dump_file(event_dict, ddir, "10-merged-events", "json")

        logging.info("Made {} API calls".format(_num_api_calls))


    nice_json, filtered_json, virtual_json, old_ids \
      = prepare_event_lists(event_dict)
    clean_event_dict(event_dict, old_ids)

    if DUMP:
        dump_file(nice_json, ddir, "15-nice-events", "json")
        dump_file(filtered_json, ddir, "20-filtered-events", "json")
        dump_file(virtual_json, ddir, "25-virtual-events", "json")
        dump_file(old_ids, ddir, "30-old-ids", "txt")

    # Incorporate into dump_file?
    with open(config.OUT_EVENT_DICT, "w", encoding='utf8') as out_events:
        json.dump(event_dict, out_events, indent=2, separators=(',', ': '))

    destpairs = []

    for transform_type in transforms:
        if transform_type == "rss":
            destpairs.append({
              'generated_file': generate_rss(
                nice_json,
                config.FEED_TITLE
                ),
              'dest': config.OUTRSS
              })
            destpairs.append({
              'generated_file': generate_rss(
                filtered_json,
                "{} - Filtered Out Events".format(config.FEED_TITLE)
                ),
              'dest': config.OUTRSS_FILTERED
              })
            destpairs.append({
              'generated_file': generate_rss(
                virtual_json,
                "{} - Virtual Events".format(config.FEED_TITLE)
                ),
              'dest': config.OUTRSS_VIRTUAL
              })

        elif transform_type == "ical":
            destpairs.append({
              'generated_file': generate_ical(
                nice_json,
                config.FEED_TITLE,
                ),
              'dest': config.OUTICAL
              })
            destpairs.append({
              'generated_file': generate_ical(
                filtered_json,
                "{} - Filtered Out Events".format(config.FEED_TITLE)
                ),
              'dest': config.OUTICAL_FILTERED
              })
            destpairs.append({
              'generated_file': generate_ical(
                virtual_json,
                "{} - Virtual Events".format(config.FEED_TITLE)
                ),
              'dest': config.OUTICAL_VIRTUAL
              })

        else:
            raise NameError("Incorrect type '%s' listed" %
              (transform_type,))

    for outpair in destpairs:
        # Insert Windows newlines for dumb email clients
        outfile = open(
          outpair['dest'], 
          "w", 
          newline='\r\n', 
          encoding='utf8',
          )
        outfile.write(outpair['generated_file'])

    logging.info("Completed run")


