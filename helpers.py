#!/usr/bin/env python3

import argparse, sys, os
import json
import requests
import jinja2
import pytz, datetime, dateutil.parser

RSS_TEMPLATE="rss_template_eventbrite.jinja2"
ICAL_TEMPLATE="ical_template_eventbrite.jinja2"


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
   base, params = url.split("?", 1)

   return base


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


# ------------------------------
def get_time_now():
   
    target_timezone = pytz.timezone(config.TIMEZONE)
    time_now = datetime.datetime.now(tz=target_timezone)

    return time_now

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
def call_api():

    BASE_URL = "https://www.eventbriteapi.com/v3"

    search_api_url = "{}/events/search/".format(
      BASE_URL,
      )

    curr_page = 1
    more_items = True

    query_args = config.QUERY_ARGS
    event_list = []

    while more_items: 
        api_params = { 
          'token': config.API_TOKEN,
          'page' : curr_page,
          'expand' : 'venue,ticket_availability,description',
          }

        api_params.update(query_args)

        r = requests.get(search_api_url, api_params)
        r.raise_for_status()
        r_json = r.json() 

        event_list = event_list + r_json['events']

        if 'error' in r_json.keys():
            more_items = False
        elif 'pagination' in r_json.keys() \
          and r_json['pagination']['has_more_items'] :
            curr_page = curr_page + 1
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
""" Print JSON nicely, because debugging is frustrating.
"""
def print_json(j):
    print(json.dumps(j, indent=2, separators=(',', ': ')))



# ------------------------------
def generate_ical(cal_dict):
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
      "feed_title": config.FEED_TITLE,
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
def generate_rss(cal_dict):
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

    time_now = get_time_now()
    time_now_formatted = time_now.strftime("%a, %d %b %Y %T %z")

    template = template_env.get_template( RSS_TEMPLATE ) 
    template_vars = { 
      "feed_title": config.FEED_TITLE,
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

    return output_rss

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

    if configfile: 
        config_location=configfile
    else: 
        config_location = DEFAULT_CONFIG_SOURCEFILE

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

    args = parser.parse_args()
    if args.configfile:
        config_location = os.path.abspath(args.configfile)


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

    # For test harness
    return config
            


# ------------------------------
def write_transformation(transforms):
    """ Write file(s) for the transformation. The transforms should
        be a list of strings that contain 'rss' or 'ical'.
        If I was a better programmer then I would force this.
    """

    load_config() 

    cal_json = call_api() 

    outjson = open(config.OUTJSON, "w", encoding='utf8')
    json.dump(cal_json, outjson, indent=2, separators=(',', ': '))

    destpairs = []

    for transform_type in transforms:
        if transform_type == "rss":
            destpairs.append({
              'generated_file': generate_rss(cal_json),
              'dest': config.OUTRSS
              })

        elif transform_type == "ical":
            destpairs.append({
              'generated_file': generate_ical(cal_json),
              'dest': config.OUTICAL
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

