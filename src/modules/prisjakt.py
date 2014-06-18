
import asyncio
import json
import urllib.parse

import aiohttp

import waterbug

class Commands:

    @waterbug.expose
    class prisjakt:

        @waterbug.expose
        @asyncio.coroutine
        def search(responder, *line):
            qstring = urllib.parse.urlencode({
                "class": "Search_Supersearch",
                "method": "search",
                "skip_login": 1,
                "modes": "product",
                "limit": 3,
                "q": responder.line
            })
            url = "http://www.prisjakt.nu/ajax/server.php?{}".format(qstring)

            print("Running search")
            try:
                response = yield from asyncio.wait_for(aiohttp.request('GET', url), 5)
            except (asyncio.TimeoutError, aiohttp.HttpException):
                responder("Couldn't fetch result")
                return
            print("Ran search")

            body = json.loads((yield from response.read_and_close()).decode('utf-8'))
            product = body['message']['product']

            if len(product['items']) > 0:
                for item in body['message']['product']['items']:
                    responder("{name} ({price[display]}) - {url}".format(**item))

                if product['more_hits_available']:
                    responder("More: http://www.prisjakt.nu/search.php?{}".format(
                        urllib.parse.urlencode({"s": responder.line})))
            else:
                responder("No products found")
