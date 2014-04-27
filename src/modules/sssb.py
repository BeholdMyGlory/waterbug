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

import waterbug

class Commands:

    def init():
        asyncio.async(Commands.fetch_new_apartments())

    @waterbug.expose
    @asyncio.coroutine
    def sssb(responder):
        try:
            data = yield from waterbug.fetch_url(
                "GET", "https://www.sssb.se/widgets/?paginationantal=all&" \
                       "callback=&widgets[]=objektlistabilder%40lagenheter")
            # remove initial '(' and final ');'
            data = json.loads(data[1:-2].decode('utf-8'))
        except asyncio.TimeoutError:
            LOGGER.warning("Couldn't fetch SSSB JSON")
            return
        except ValueError:
            LOGGER.warning("Got invalid JSON")
            return

        for apartment in data['data']['objektlistabilder@lagenheter']['objekt']:
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

            responder("[{omrade}] {typOvergripande} {yta} m² · {adress} ({vaning}) · {hyra} · " \
                      "bokning {bokning} · {antalIntresse} · {url}".format(
                          url=shorturl, bokning=booking_date, **apartment))
            yield from asyncio.sleep(1) # avoid flooding

