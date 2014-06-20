
import asyncio
import json
import re
import urllib.parse

import waterbug

parser = waterbug.ArgumentParser()
parser.add_argument('-f', default="sv")
parser.add_argument('-t', default="en")
parser.add_argument('string', nargs='+')

class Commands:

    @waterbug.expose
    @asyncio.coroutine
    def translate(responder, *text):
        ns = parser.parse_args(text)
        qstring = urllib.parse.urlencode({
            "client": "t",
            "sl": ns.f,
            "tl": ns.t,
            "dt": "t",
            "ie": "UTF-8",
            "oe": "UTF-8",
            "q": " ".join(ns.string)
        })
        body = yield from waterbug.fetch_url(
            "https://translate.google.com/translate_a/single?" + qstring, method="GET",
            headers={"User-Agent": ""})
        res = json.loads(re.sub(',(?=,)', ',null', body.decode('utf-8')))
        responder(res[0][0][0])
