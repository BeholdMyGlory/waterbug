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

all_locations = set()
apartmenttypes = {"studentrum", "studentetta", "studentlägenhet"}

filters = STORAGE.get_data()

checks = {
    "locations": lambda apartment, x: apartment['omradeKod'].lower() in x,
    "apartmenttype": lambda apartment, x: apartment['typOvergripande'].lower() in x,
    "maxrent": lambda apartment, x: apartment['hyra'] <= x,
    "minarea": lambda apartment, x: apartment['yta'] >= x,
    "maxqueuedays": lambda apartment, x: apartment['kodagar'] <= x
}

class Commands(waterbug.Commands):

    @asyncio.coroutine
    def init():
        global all_locations
        data = yield from Commands.fetch_raw_apartments()
        locations_html = lxml.etree.HTML(data['html']['objektfilter@lagenheter'])
        all_locations = set(option.get('value').lower()
                            for option in locations_html.findall(".//select[@id='omraden']/option")
                            if len(option.get('value')) > 0)


    @waterbug.periodic(60*60, trigger_on_start=True)
    @asyncio.coroutine
    def fetch_new_apartments():
        LOGGER.info("Fetching apartments")

        old_apartments = filters.get("seen_apartments", set())
        filters['seen_apartments'] = set()
        for apartment in (yield from Commands.fetch_apartments()):
            filters['seen_apartments'].add((apartment['omrade'], apartment['adress'],
                                            apartment['kodagar']))
            if (apartment['omrade'], apartment['adress'], apartment['kodagar']) in old_apartments:
                continue

            for k, fltrs in filters.items():
                if k == 'seen_apartments':
                    continue

                server, channel, user = k
                if any(all(checks[valname](apartment, val)
                           for valname, val in fltr.items())
                       for fltr in fltrs):
                    message = yield from Commands.format_message(apartment)
                    BOT.queue_message(server, channel, user, message)

        STORAGE.sync()
        LOGGER.info("Fetched apartments")

    @asyncio.coroutine
    def format_message(apartment):
        shorturl = yield from Commands.shorten_url(apartment['detaljUrl'])
        booking_date = yield from Commands.fetch_booking_date(apartment['detaljUrl'])

        return "[{omrade}] {typOvergripande} {yta} m² · {egenskaper} · " \
               "{adress} ({vaning}) · {hyra} kr/mån · bokning {bokning} · " \
               "inflyttning {inflyttningDatum} · {antalIntresse} · {url}".format(
                   url=shorturl, bokning=booking_date, **apartment)

    @asyncio.coroutine
    def fetch_raw_apartments():
        data = yield from waterbug.fetch_url(
            "https://www.sssb.se/widgets/?paginationantal=all&" \
            "callback=&widgets[]=objektlistabilder%40lagenheter&" \
            "widgets[]=objektfilter%40lagenheter")
        # remove initial '(' and final ');'
        data = json.loads(data[1:-2].decode('utf-8'))
        return data

    @asyncio.coroutine
    def fetch_apartments():
        data = yield from Commands.fetch_raw_apartments()
        apartments = sorted(data['data']['objektlistabilder@lagenheter']['objekt'],
                            key=lambda x: x['omrade'])
        for apartment in apartments:
            days, number = re.match("(\d+) \((\d+)st\)", apartment['antalIntresse']).groups()
            apartment['kodagar'] = int(days)
            apartment['antal'] = int(number)

            apartment['hyra'] = int(apartment['hyra'])

            prop = [('1015', 'M'), ('3025', 'T'), ('1036', 'E')]
            egenskaper = {egenskap['id'] for egenskap in apartment['egenskaper']}
            apartment['egenskaper'] = "{}{}{}".format(*(e if i in egenskaper else '-'
                                                        for i, e in prop))
        return apartments

    @asyncio.coroutine
    def fetch_booking_date(detaljUrl):
        refid = urllib.parse.urlparse(detaljUrl).query
        booking_data = yield from waterbug.fetch_url(
            "https://www.sssb.se/widgets/?{}&" \
            "callback=&widgets[]=objektintresse".format(refid))
        booking_data = json.loads(booking_data[1:-2].decode('utf-8'))
        booking_date, booking_time = re.search('Kan bokas till ([^ ]+) klockan ([^< ]+)',
                                                booking_data['html']['objektintresse']).groups()
        return booking_date

    @asyncio.coroutine
    def shorten_url(url):
        data = yield from waterbug.fetch_url(
            "https://www.googleapis.com/urlshortener/v1/url?key={}".format(
                CONFIG['googlkey']),
            method="POST", data=json.dumps({"longUrl": url}),
            headers={"Content-Type": "application/json"})
        return json.loads(data.decode('utf-8'))['id']

    @waterbug.expose
    class sssb:

        @waterbug.expose(flags=True, require_auth=True)
        def addfilter(responder, *, locations:str=None,
                      apartmenttype:str=None, maxrent:int=-1, minarea:int=-1,
                      maxqueuedays:int=-1):
            if locations is not None:
                locations = set(locations.lower().split(','))
                for location in locations:
                    if location not in all_locations:
                        responder("Okänt område {}; tillgängliga områden: {}".format(
                            location, ", ".join(all_locations)))
                        return

            if apartmenttype is not None:
                apartmenttype = set(apartmenttype.lower().split(','))
                for at in apartmenttype:
                    if at not in apartmenttypes:
                        responder("Okänd lägenhetstyp {}; tillgängliga lägenhetstyper: {}".format(
                            at, ", ".join(apartmenttypes)))
                        return

            defaults = {
                "locations": None,
                "apartmenttype": None,
                "maxrent": -1,
                "minarea": -1,
                "maxqueuedays": -1
            }

            filters.setdefault((responder.server.name, responder.target, responder.sender.account),
                               []).append({
                valname: val
                for valname, val in [('locations', locations), ('apartmenttype', apartmenttype),
                                     ('maxrent', maxrent), ('minarea', minarea),
                                     ('maxqueuedays', maxqueuedays)]
                if val != defaults[valname]
            })

            STORAGE.sync()
            responder("Filter added")

        @waterbug.expose(require_auth=True)
        def clearfilters(responder):
            if (responder.server.name, responder.target, responder.sender.account) in filters:
                del filters[(responder.server.name, responder.target, responder.sender.account)]
                STORAGE.sync()
                responder("All filters cleared")
            else:
                responder("No filters added")

        @waterbug.expose(require_auth=True)
        def listfilters(responder):
            names = {
                "locations": "Locations",
                "apartmenttype": "Apartment type",
                "maxrent": "Maximum rent",
                "minarea": "Minimum floor area",
                "maxqueuedays": "Maximum queueing days"
            }

            if (responder.server.name, responder.target, responder.sender.account) not in filters:
                responder("No filters added")
            else:
                for filt in filters[(responder.server.name, responder.target,
                                     responder.sender.account)]:
                    if len(filt) == 0:
                        responder("(No filter)")
                    else:
                        responder("; ".join("{}: {}".format(names[valname], filt[valname])
                                            for valname in sorted(filt)))

        @waterbug.expose(require_auth=True)
        def listmatches(responder):
            if (responder.server.name, responder.target, responder.sender.account) not in filters:
                responder("No filters added")
            else:
                fltrs = filters[(responder.server.name, responder.target,
                                 responder.sender.account)]
                no_matches = True
                for apartment in (yield from Commands.fetch_apartments()):
                    if any(all(checks[valname](apartment, val)
                               for valname, val in fltr.items())
                           for fltr in fltrs):
                        no_matches = False
                        responder((yield from Commands.format_message(apartment)))

                if no_matches:
                    responder("No matching items found")


asyncio.async(Commands.init())
