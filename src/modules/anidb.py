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
import itertools
import re
import urllib.request
import xml.etree.ElementTree as ElementTree

import aiohttp
import feedparser

import waterbug

class Commands(waterbug.Commands):

    @waterbug.trigger
    def unload():
        del Commands.anidb.titles

    @waterbug.expose
    class anidb:

        def init():
            global anidb
            anidb = Commands.anidb

            anidb.titles = anidb.load_titles(open("animetitles.xml"))
            anidb.cache = {}
            anidb.url_info = CONFIG

            anidb.read_from_feed = set()

            anidb.watchedtitles = STORAGE.get_data().setdefault("watched", {})

        def load_titles(file):
            titles = {}
            for (event, elem) in ElementTree.iterparse(file, ("start", "end")):
                if event == "start" and elem.tag == "anime":
                    currentanime = {}
                    titles[int(elem.attrib['aid'])] = currentanime
                if event == "end" and elem.tag == "title":
                    if elem.attrib['type'] not in currentanime:
                        currentanime[elem.attrib['type']] = {}
                    if elem.attrib['{http://www.w3.org/XML/1998/namespace}lang'] not in currentanime[elem.attrib['type']]:
                        currentanime[elem.attrib['type']][elem.attrib['{http://www.w3.org/XML/1998/namespace}lang']] = []
                    currentanime[elem.attrib['type']][elem.attrib['{http://www.w3.org/XML/1998/namespace}lang']].append(elem.text)
            return titles

        def fetch_anime(aid):
            if aid in anidb.cache:
                return anidb.cache[aid]

            info = {}
            info_file = yield from waterbug.fetch_url(
                "http://{server}:{port}/httpapi?request=anime&client={clientname}"
                "&clientver={clientversion}&protover={protoversion}&aid={aid}".format(
                    aid=aid, **anidb.url_info))

            root = ElementTree.fromstring(info_file)
            if root.tag == "error":
                raise IOError(root.getroot().text)

            info["type"] = root.find("type").text
            info["episodecount"] = int(root.find("episodecount").text)
            info["startdate"] = getattr(root.find("startdate"), "text", "???")
            info["enddate"] = getattr(root.find("enddate"), "text", "???")
            info["relatedanime"] = []
            tmp = root.find("relatedanime")
            if tmp is not None:
                for anime in tmp:
                    info["relatedanime"].append({"aid": int(anime.attrib['id']), "type": anime.attrib['type'],
                                                 "title": anime.text})
            info["similaranime"] = []
            tmp = root.find("similaranime")
            if tmp is not None:
                for anime in tmp:
                    info["similaranime"].append({"aid": int(anime.attrib['id']), "title": anime.text,
                                                 "approval": int(anime.attrib['approval']),
                                                 "total": int(anime.attrib['total']),
                                                 "percentage": round(100*int(anime.attrib['approval']) /
                                                                         int(anime.attrib['total']), 2)})
            info["similaranime"].sort(key=lambda x: x['percentage'], reverse=True)
            info["categories"] = []
            tmp = root.find("categories")
            if tmp is not None:
                info["categories"] = list(map(lambda x: {"name": x.find("name").text,
                                                         "weight": int(x.attrib['weight'])},
                                              sorted(list(tmp), key=lambda x: int(x.attrib['weight']),
                                                     reverse=True)))
            info["rating"] = getattr(root.find("ratings/permanent"), "text", "???")

            anidb.cache[aid] = info

            return info

        @waterbug.periodic(120)
        @asyncio.coroutine
        def update_feed():
            try:
                LOGGER.info("Fetching anidb atom feed")
                feed = yield from waterbug.fetch_url("http://anidb.net/feeds/files.atom")
            except asyncio.TimeoutError, aiohttp.HttpException:
                LOGGER.warning("Couldn't fetch anidb atom feed")
                return

            for entry in feedparser.parse(feed)["entries"]:
                if entry["id"] in anidb.read_from_feed:
                    continue # already checked item

                title = entry['title']
                link = entry['link']
                content = ElementTree.fromstring(entry["content"][0]["value"])
                try:
                    group = re.search("\((.+)\)$", content.find("dd[7]").text).group(1)
                except AttributeError:
                    continue # couldn't retrieve group name

                for aid, targets in anidb.watchedtitles.items():
                    if title.startswith(anidb.titles[aid]["main"]["x-jat"][0]):
                        anidb.read_from_feed.add(entry["id"])
                        for (network, channel), wanted_group in targets.items():
                            if network in anidb.bot.servers and \
                                    channel in anidb.bot.servers[network].channels and \
                                    (wanted_group is None or wanted_group.lower() == group.lower()):
                                anidb.bot.servers[network].msg(
                                    channel, "New file added: {} - {}".format(title, link))


        def _search(animetitle, find_exact_match=False, limit=None):
            animetitle = animetitle.lower().strip().replace("'", "`")
            keywords = animetitle.split()
            results = {}

            for aid, titles in anidb.titles.items():
                match = False
                for langs in titles.values():
                    for titlelist in langs.values():
                        for title in titlelist:
                            title = title.lower()
                            if find_exact_match and title == animetitle:
                                return {aid: titles}
                            if all(keyword in title for keyword in keywords):
                                match = True

                if match:
                    if limit is None or len(results) < limit:
                        results[aid] = titles
                    elif not find_exact_match:
                        break

            return results

        def format_title(titles):
            t = []
            for type_, lang in (("official", "en"), ("main", "x-jat"), ("official", "ja")):
                if type_ in titles and lang in titles[type_]:
                    t.append(titles[type_][lang][0])
            if len(t) == 3:
                return "{t[0]} ({t[2]} {t[1]})".format(t=t)
            elif len(t) == 2:
                return "{} ({})".format(*t)
            else:
                return t[0]


        @waterbug.expose
        @asyncio.coroutine
        def _default(responder, *args):
            r = anidb._search(responder.line, True, 1)
            if len(r) == 0:
                responder("Anime not found")
                return

            aid, titles = next(iter(r.items()))
            info = yield from anidb.fetch_anime(aid)
            responder("{}, {}, aired {}, {} episode(s), rating: {}, [{}] - http://anidb.net/a{}" \
                       .format(anidb.format_title(titles), info['type'],
                               info['startdate'] if info['startdate'] == info['enddate'] else "{}­­–{}" \
                                        .format(info['startdate'], info['enddate']), info['episodecount'],
                               info['rating'], ", ".join(map(lambda x: x['name'], info['categories'][:9])), aid))

        @waterbug.expose
        def search(responder, *args):
            r = anidb._search(responder.line, limit=4)
            for aid, titles in r.items():
                responder("{} - http://anidb.net/a{}".format(anidb.format_title(titles), aid))
            if len(r) == 0:
                responder("No anime found")

        @waterbug.expose
        @asyncio.coroutine
        def similar(responder, *args):
            r = anidb._search(responder.line, True, 1)
            if len(r) == 0:
                responder("Anime not found")
                return

            aid, _ = next(iter(r.items()))
            info = yield from anidb.fetch_anime(aid)
            if len(info["similaranime"]) == 0:
                responder("No similar anime found")
                return

            for i in itertools.islice(info["similaranime"], 3):
                responder("{}% - {} - http://anidb.net/a{}".format(i["percentage"], i["title"], i["aid"]))

            if len(info["similaranime"]) > 3:
                responder("More: http://anidb.net/perl-bin/animedb.pl?show=addsimilaranime&aid={}".format(aid))

        @waterbug.expose
        @asyncio.coroutine
        def related(responder, *args):
            r = anidb._search(responder.line, True, 1)
            if len(r) == 0:
                responder("Anime not found")
                return

            aid, _ = next(iter(r.items()))
            info = yield from anidb.fetch_anime(aid)
            if len(info["relatedanime"]) == 0:
                responder("No related anime found")
                return

            for i in itertools.islice(info["relatedanime"], 3):
                responder("{}: {} - http://anidb.net/a{}".format(i["type"], i["title"], i["aid"]))

            if len(info["relatedanime"]) > 3:
                responder("More: http://anidb.net/perl-bin/animedb.pl?show=addseq&aid={}".format(aid))

        @waterbug.expose
        def add(responder, *args):
            try:
                group, searchterms = responder.line.split(' ')
                group = re.match("^\[(.+)\]$", group).group(1)
            except (AttributeError, ValueError):
                group = None
                searchterms = responder.line

            r = anidb._search(searchterms, True, 1)
            if len(r) == 0:
                responder("Anime not found")
                return

            aid, titles = next(iter(r.items()))
            anidb.watchedtitles.setdefault(aid, {})[(responder.server.name, responder.target)] = group
            STORAGE.sync()
            responder("Added {} [{}]".format(titles["main"]["x-jat"][0], group))

        @waterbug.expose
        def remove(responder, *args):
            r = anidb._search(responder.line, True, 1)
            if len(r) == 0:
                responder("Anime not found")
                return

            aid, titles = next(iter(r.items()))
            if (aid not in anidb.watchedtitles or
                    (responder.server.name, responder.target) not in anidb.watchedtitles[aid]):
                responder("You are not following this anime")
                return

            del anidb.watchedtitles[aid][(responder.server.name, responder.target)]
            if len(anidb.watchedtitles[aid]) == 0:
                del anidb.watchedtitles[aid]
            STORAGE.sync()
            responder("Removed '{}' from the watchlist".format(titles["main"]["x-jat"][0]))

        @waterbug.expose(name="list")
        def list_(responder):
            hasitems = False
            for aid, info in anidb.watchedtitles.items():
                if (responder.server.name, responder.target) in info:
                    responder("{} [{}]".format(anidb.titles[aid]["main"]["x-jat"][0],
                                               info[(responder.server.name, responder.target)]),
                              msgtype='NOTICE')
                    hasitems = True

            if not hasitems:
                responder("You are not following any animes")

Commands.anidb.init()
