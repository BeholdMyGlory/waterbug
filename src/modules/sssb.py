#   Waterbug, a modular IRC bot written using Python 3
#   Copyright (C) 2011  Arvid Fahlström Myrman
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <http://www.gnu.org/licenses/>.

import asyncio
import json
import re
import urllib.parse

import aiohttp
import lxml.etree

import waterbug

class Commands:

    def init():
        asyncio.async(Commands.fetch_new_apartments())

    @asyncio.coroutine
    @waterbug.expose(flags=True)
    def sssb(responder, *, maxdays:int=-1, locations:str=None,
             apartmenttype:str=None, maxrent:int=-1, minarea:int=-1,
             maxqueuedays:int=-1):
        try:
            data = yield from waterbug.fetch_url(
                "GET", "https://www.sssb.se/widgets/?paginationantal=all&" \
                       "callback=&widgets[]=objektlistabilder%40lagenheter&" \
                       "widgets[]=objektfilter%40lagenheter")
            # remove initial '(' and final ');'
            data = json.loads(data[1:-2].decode('utf-8'))
        except asyncio.TimeoutError:
            LOGGER.warning("Couldn't fetch SSSB JSON")
            return
        except ValueError:
            LOGGER.warning("Got invalid JSON")
            return

        locations_html = lxml.etree.HTML(data['html']['objektfilter@lagenheter'])
        locations_sssb = set(option.get('value').lower()
                             for option in
                                locations_html.findall(".//select[@id='omraden']/option")
                             if len(option.get('value')) > 0)

        if locations is None:
            locations = locations_sssb
        else:
            locations = set(locations.lower().split(','))
            for location in locations:
                if location not in locations_sssb:
                    responder("Okänt område {}; tillgängliga områden: {}".format(
                        location, ", ".join(locations_sssb)))
                    return

        apartmenttypes = {"studentrum", "studentetta", "studentlägenhet"}
        if apartmenttype is None:
            apartmenttype = apartmenttypes
        else:
            apartmenttype = set(apartmenttype.lower().split(','))
            for at in apartmenttype:
                if at not in apartmenttypes:
                    responder("Okänd lägenhetstype {}; tillgängliga lägenhetstyper: {}".format(
                        at, ", ".join(apartmenttypes)))
                    return

        no_results = True
        apartments = sorted(data['data']['objektlistabilder@lagenheter']['objekt'],
                            key=lambda x: x['omrade'])
        for apartment in apartments:
            days, number = re.match("(\d+) \((\d+)st\)", apartment['antalIntresse']).groups()
            days, number = int(days), int(number)

            if (apartment['omradeKod'].lower() not in locations
                or apartment['typOvergripande'].lower() not in apartmenttype
                or (maxrent >= 0 and int(apartment['hyra']) > maxrent)
                or (minarea >= 0 and int(apartment['yta']) < minarea)
                or (maxqueuedays >= 0 and days > maxqueuedays)):
                continue

            no_results = False
            data = yield from waterbug.fetch_url(
                "POST", "https://www.googleapis.com/urlshortener/v1/url?key={}".format(
                    CONFIG['googlkey']),
                data=json.dumps({"longUrl": apartment['detaljUrl']}),
                headers={"Content-Type": "application/json"})
            shorturl = json.loads(data.decode('utf-8'))['id']

            refid = urllib.parse.urlparse(apartment['detaljUrl']).query
            booking_data = yield from waterbug.fetch_url(
                "GET", "https://www.sssb.se/widgets/?{}&" \
                       "callback=&widgets[]=objektintresse".format(refid))
            booking_data = json.loads(booking_data[1:-2].decode('utf-8'))
            booking_date, booking_time = re.search('Kan bokas till ([^ ]+) klockan ([^< ]+)',
                                                   booking_data['html']['objektintresse']).groups()

            responder("[{omrade}] {typOvergripande} {yta} m² · {adress} ({vaning}) · " \
                      "{hyra} kr/mån · bokning {bokning} · {antalIntresse} · {url}".format(
                          url=shorturl, bokning=booking_date, **apartment))
            yield from asyncio.sleep(1) # avoid flooding

        if no_results:
            responder("Hittade inga matchande lägenheter")
