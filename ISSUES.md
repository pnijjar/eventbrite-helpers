- Eventbrite does not store full descriptions in the descriptions
  field, and you need a second API call to get everything.
  + The versions that are bad include: 3.7.0 . 
  + The only other version I see is 3.0.0, which is okay. 

- The currency is assumed to be dollars. I guess we can have a 
  variable to set this in config.py
 
- Eventbrite has severely limited the search API, as of October 2019.
  So the RSS feeds have gotten a lot shorter. Ideally we would 
  retrieve events without destroying the old feed.
