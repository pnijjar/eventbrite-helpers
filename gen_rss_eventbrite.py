#!/usr/bin/env python3 

import helpers as h

h.load_config()
events = h.call_api()
#h.print_results(results)
outrss = h.generate_rss(events)

print(outrss)
