
import asyncio
import json
import re
import time
import urllib.parse

import aiohttp
import feedparser
import lxml.html

import waterbug

login_lock = asyncio.Lock()
login_cookie = None
url_regex = re.compile("^(?:(?:http://)?(?:www\.)?prisjakt\.nu/produkt\.php\?p=)?(\d+)$")
rss_url = "http://www.prisjakt.nu/minapriser.rss?user=" + CONFIG['username'] + "&.rss"

watchers = STORAGE.get_data()

class Commands(waterbug.Commands):

    @waterbug.expose
    class prisjakt:

        @waterbug.periodic(60*60, trigger_on_start=True)
        @asyncio.coroutine
        def fetch_feed():
            LOGGER.info("Fetching feed")
            body = yield from waterbug.fetch_url(rss_url)
            feed = feedparser.parse(body)

            old_entries = watchers.get('read_entries', set())
            watchers['read_entries'] = set()
            for entry in feed['entries']:
                if entry['id'] not in old_entries:
                    link = entry['link'].split("#")[0]
                    prod_id = url_regex.match(link).group(1)
                    message = "[Prisjakt update] {} - {}".format(entry['title'], link)

                    for server, channel, user in watchers.get(prod_id, set()):
                        BOT.queue_message(server, channel, user, message)
                watchers['read_entries'].add(entry['id'])
            STORAGE.sync()
            LOGGER.info("Fetched feed")

        @asyncio.coroutine
        def login():
            global login_cookie
            with (yield from login_lock):
                if login_cookie is None:
                    response, body = yield from Commands.prisjakt.server_request(
                        "C_LoginAndRegistration", "login_user",
                        username=CONFIG['username'], password=CONFIG['password'],
                        request_id=1, raw_response=True, ensure_logged_in=False)
                    if body['error']:
                        raise Exception(body['message'])
                    else:
                        login_cookie = response.cookies

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

            try:
                response = yield from asyncio.wait_for(aiohttp.request('GET', url), 5)
            except (asyncio.TimeoutError, aiohttp.HttpException):
                responder("Couldn't fetch result")
                return

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

        @asyncio.coroutine
        def ajax_request(m, p):
            yield from Commands.prisjakt.login()
            response = yield from asyncio.wait_for(aiohttp.request(
                'POST', "http://www.prisjakt.nu/ajax/jsonajaxserver.php", data={
                    "m": m,
                    "p": json.dumps(p),
                    "t": int(time.time()*1000)
                }, cookies=login_cookie), 5)
            raw_body = (yield from response.read_and_close()).decode('utf-8')
            # r'<\!--HAHA --\>', which is returned by bevaka_form, is an invalid JSON string
            raw_body = raw_body.replace(r"\!", "!").replace(r"\>", ">")
            body = json.loads(raw_body[len("<!-- START JSON OUTPUT:"):-len("END JSON OUTPUT -->")])
            return body

        @asyncio.coroutine
        def server_request(cls, method, data=None, raw_response=False,
                           ensure_logged_in=True, **params):
            if ensure_logged_in:
                yield from Commands.prisjakt.login()

            params['class'] = cls
            params['method'] = method
            if data is not None:
                params['data'] = json.dumps(data)

            args = {"data": params}
            if ensure_logged_in:
                args['cookies'] = login_cookie

            response = yield from asyncio.wait_for(aiohttp.request(
                'POST', 'http://www.prisjakt.nu/ajax/server.php', **args), 5)
            body = json.loads((yield from response.read_and_close()).decode('utf-8'))
            if raw_response:
                return response, body
            else:
                return body

        @asyncio.coroutine
        def get_watched_list():
            body = yield from Commands.prisjakt.server_request(
                "C_Sidebar", "save_lists", data=[{
                    'current_sort': 'alpha',
                    'list_id': 'Watch',
                }])
            return body['message'][0]['saved']['items']

        @waterbug.expose(require_auth=True)
        @asyncio.coroutine
        def watch(responder, *urls):
            prod_ids = {}

            for url in urls:
                match = url_regex.match(url)
                if match is None:
                    responder("Invalid URL or product ID: {}".format(url))
                    return
                else:
                    prod_ids[match.group(1)] = "http://www.prisjakt.nu/produkt.php?p={}".format(
                        match.group(1))

            for prod_id in prod_ids:
                if prod_id not in watchers:
                    body = yield from Commands.prisjakt.ajax_request("bevaka_save", {
                        "base_type": "1",
                        "item_id": prod_id,
                        "email_alert": 0,
                        "push_alert": 0,
                        "price_alert_type": "price_in_stock",
                        "lovehate": "normal",
                        "price_drop_type": "drops"
                    })
                    if body['error']:
                        responder("Watch request failed for product ID {}".format(prod_id))
                        LOGGER.error(body)
                        continue

                    watchers[prod_id] = set()

            items = yield from Commands.prisjakt.get_watched_list()
            for item in items:
                prod_id = item['item_id']
                if prod_id not in prod_ids:
                    continue

                if (responder.server.name, responder.target,
                        responder.sender.account) in watchers[prod_id]:
                    responder("User registered as {} is already watching {}".format(
                        responder.sender.account, item['name']))
                else:
                    watchers[prod_id].add((responder.server.name, responder.target,
                                        responder.sender.account))
                    responder("User registered as {} is now watching {} - {}".format(
                        responder.sender.account, item['name'], prod_ids[prod_id]))

            STORAGE.sync()


        @waterbug.expose(require_auth=True)
        @asyncio.coroutine
        def unwatch(responder, *urls):
            prod_ids = {}

            for url in urls:
                match = url_regex.match(url)
                if match is None:
                    responder("Invalid URL or product ID: {}".format(url))
                    return
                else:
                    prod_ids[match.group(1)] = "http://www.prisjakt.nu/produkt.php?p={}".format(
                        match.group(1))

            items = yield from Commands.prisjakt.get_watched_list()
            for item in items:
                prod_id = item['item_id']
                if prod_id not in prod_ids:
                    continue

                if prod_id not in watchers or (responder.server.name, responder.target,
                                               responder.sender.account) not in watchers[prod_id]:
                    responder("Not currently watching {}".format(item['name']))
                    return
                else:
                    watchers[prod_id].remove((responder.server.name, responder.target,
                                              responder.sender.account))
                    responder("User registered as {} is no longer watching {}".format(
                        responder.sender.account, item['name']))

                if len(watchers[prod_id]) == 0:
                    del watchers[prod_id]

                    body = yield from Commands.prisjakt.ajax_request("bevaka_remove", {
                        "alert_id": item['listitem_id']
                    })

                    if body['error']:
                        responder("Something went wrong when trying to remove watched item")
                        LOGGER.error(body)

            STORAGE.sync()

        @waterbug.expose(require_auth=True)
        @asyncio.coroutine
        def list(responder):
            items = yield from Commands.prisjakt.get_watched_list()
            watched_item_found = False
            if len(items) > 0:
                for item in items:
                    if (responder.server.name, responder.target,
                            responder.sender.account) in watchers.get(item['item_id'], []):
                        watched_item_found = True
                        responder("{name} ({price}) - http://www.prisjakt.nu/produkt.php" \
                                  "?p={item_id}".format(**item), msgtype="NOTICE")

            if not watched_item_found:
                responder("No watched items")

