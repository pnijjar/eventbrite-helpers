#!/usr/bin/env python3

import argparse, sys, os
import json
import requests

# ------------------------------
def call_api():

    BASE_URL = "https://www.eventbriteapi.com/v3"

    api_url = "{}/events/search/".format(
      BASE_URL,
      )

    curr_page = 1
    more_items = True

    while more_items: 

        api_params = { 
          'token': config.API_TOKEN,
          'page' : curr_page,
          'expand' : 'venue',

          # This does not seem to work??
          'location.address' : 'Kitchener',
          'location.within' : '15km',
          #'location.latitude' : "43.451640",
          #'location.longitude' : "-80.492534",
          #'categories' : '102,113',
          #'q' : "counselling",
        }

        r = requests.get(api_url, api_params)
        r_json = r.json() 
        print(json.dumps(r_json, indent=2, sort_keys=True))

        for event in r_json['events']:
            location = "Not Specified"
            if 'localized_address_display' in event['venue']['address'].keys():
                location = event['venue']['address']['localized_address_display']

         #   print("{}\n{}\n{}\n{}\n\n".format(
         #     event['name']['text'],
         #     event['start']['local'],
         #     event['url'],
         #     location,
         #     ))


        if 'error' in r_json.keys():
            more_items = False
        elif 'pagination' in r_json.keys() \
          and r_json['pagination']['has_more_items'] :
            curr_page = curr_page + 1
            more_items = True
        else:
            more_items = False







# ------------------------------
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
        'secrets',
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
            
