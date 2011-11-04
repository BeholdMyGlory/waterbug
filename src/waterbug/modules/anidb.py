
import gzip
import itertools
import re
import threading
import urllib.request
import xml.etree.ElementTree as ElementTree

import feedparser

import waterbug.util as wutil
import waterbug.waterbug as waterbug

class Commands:
    
    def __init__(self, data):
        self.anidb.load_data(data)
    
    @waterbug.trigger
    def unload(self):
        self.anidb.feedupdater.stop()
        del self.anidb.titles
    
    class AnidbCommands:
        
        def __init__(self):
            self.titles = self.load_titles(open("animetitles.xml"))
            self.cache = {}
            self.url_info = {
                    "server": "api.anidb.net",
                    "port": 9001,
                    "protoversion": 1,
                    "clientname": "eldishttp",
                    "clientversion": 1
            }
            
            self.read_from_feed = set()
            
            class Timer(threading.Thread):
                def __init__(self, anidb):
                    super().__init__()
                    self.event = threading.Event()
                    self.anidb = anidb
                
                def run(self):
                    while True:
                        self.event.wait(30)
                        if self.event.is_set():
                            break
                        self.anidb.update_feed()
                
                def stop(self):
                    self.event.set()
            
            self.feedupdater = Timer(self)
            self.feedupdater.start()
        
        def load_data(self, data):
            self.data = data
            self.watchedtitles = data.get_data().setdefault("watched", {})
        
        def load_titles(self, file):
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
        
        def fetch_anime(self, aid):
            if aid in self.cache:
                return self.cache[aid]
            
            info = {}
            info_file = gzip.GzipFile(fileobj=urllib.request.urlopen(
                                        "http://{server}:{port}/httpapi?request=anime&client={clientname}"
                                        "&clientver={clientversion}&protover={protoversion}&aid={aid}".format(
                                                                                    aid=aid, **self.url_info),
                                        timeout=5))
            
            root = ElementTree.parse(info_file)
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
            
            self.cache[aid] = info
            
            return info
        
        def update_feed(self):
            feed = feedparser.parse("http://anidb.net/feeds/files.atom")
            new_entries = set()
            for i in feed["entries"]:
                title, link = i["title"], i["link"]
                
                for aid, targets in self.watchedtitles.items():
                    if title.startswith(self.titles[aid]["main"]["x-jat"][0]):
                        new_entries.add(i["id"])
                        if i["id"] not in self.read_from_feed:
                            for ((network, channel), group) in targets.items():
                                if group is None or re.findall("\[(.*?)\]", title)[-1].lower() == group.lower():
                                    self.bot.servers[network].msg(channel, "New file added: {} - {}".format(title, link))
                        break
            
            self.read_from_feed = new_entries
        
        def _search(self, animetitle, find_exact_match=False, limit=None):
            animetitle = animetitle.lower().strip()
            keywords = animetitle.split()
            results = {}
            
            for aid, titles in self.titles.items():
                match = False
                for langs in titles.values():
                    for titlelist in langs.values():
                        for title in titlelist:
                            title = title.lower()
                            if find_exact_match and title == animetitle:
                                return {aid: titles}
                            if wutil.all_in(keywords, title):
                                match = True
                
                if match:
                    if limit is None or len(results) < limit:
                        results[aid] = titles
                    elif not find_exact_match:
                        break
            
            return results
        
        def format_title(self, titles):
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
        
        
        @waterbug.expose()
        def _default(self, data, server, *args):
            r = self._search(data['line'], True, 1)
            if len(r) == 0:
                server.msg(data["target"], "Anime not found")
                return
            
            aid, titles = next(iter(r.items()))
            info = self.fetch_anime(aid)
            server.msg(data["target"], "{}, {}, aired {}, {} episode(s), rating: {}, [{}] - http://anidb.net/a{}" \
                       .format(self.format_title(titles), info['type'],
                               info['startdate'] if info['startdate'] == info['enddate'] else "{}­­–{}" \
                                        .format(info['startdate'], info['enddate']), info['episodecount'],
                               info['rating'], ", ".join(map(lambda x: x['name'], info['categories'][:9])), aid))
        
        @waterbug.expose()
        def search(self, data, server, *args):
            r = self._search(data['line'], limit=4)
            for aid, titles in r.items():
                server.msg(data["target"], "{} - http://anidb.net/a{}".format(
                                                                self.format_title(titles), aid))
            if len(r) == 0:
                server.msg(data["target"], "No anime found")
        
        @waterbug.expose()
        def similar(self, data, server, *args):
            r = self._search(data['line'], True, 1)
            if len(r) == 0:
                server.msg(data["target"], "Anime not found")
                return
            
            aid, _ = next(iter(r.items()))
            info = self.fetch_anime(aid)
            if len(info["similaranime"]) == 0:
                server.msg(data["target"], "No similar anime found")
                return
            
            for i in itertools.islice(info["similaranime"], 3):
                server.msg(data["target"], "{}% - {} - http://anidb.net/a{}".format(i["percentage"], i["title"], i["aid"]))
            
            if len(info["similaranime"]) > 3:
                server.msg(data["target"], "More: http://anidb.net/perl-bin/animedb.pl?show=addsimilaranime&aid={}".format(aid))
        
        @waterbug.expose()
        def related(self, data, server, *args):
            r = self._search(data['line'], True, 1)
            if len(r) == 0:
                server.msg(data["target"], "Anime not found")
                return
            
            aid, _ = next(iter(r.items()))
            info = self.fetch_anime(aid)
            if len(info["relatedanime"]) == 0:
                server.msg(data["target"], "No related anime found")
                return
            
            for i in itertools.islice(info["relatedanime"], 3):
                server.msg(data["target"], "{}: {} - http://anidb.net/a{}".format(i["type"], i["title"], i["aid"]))
            
            if len(info["relatedanime"]) > 3:
                server.msg(data["target"], "More: http://anidb.net/perl-bin/animedb.pl?show=addseq&aid={}".format(aid))
        
        @waterbug.expose()
        def add(self, data, server, *args):
            searchterms, group = wutil.pad_iter(data['line'].rsplit(":"), 2)
            r = self._search(searchterms, True, 1)
            if len(r) == 0:
                server.msg(data["target"], "Anime not found")
                return
            
            aid, titles = next(iter(r.items()))
            self.watchedtitles.setdefault(aid, {})[(server.connection_name, data["target"])] = group
            self.data.sync()
            server.msg(data["target"], "Added {} [{}]".format(titles["main"]["x-jat"][0], group))
        
        @waterbug.expose()
        def remove(self, data, server, *args):
            r = self._search(data["line"], True, 1)
            if len(r) == 0:
                server.msg(data["target"], "Anime not found")
                return
            
            aid, titles = next(iter(r.items()))
            if aid not in self.watchedtitles or \
                                        (server.connection_name, data["target"]) not in self.watchedtitles[aid]:
                server.msg(data["target"], "You are not following this anime")
                return
            
            del self.watchedtitles[aid][(server.connection_name, data["target"])]
            if len(self.watchedtitles[aid]) == 0:
                del self.watchedtitles[aid]
            self.data.sync()
            server.msg(data["target"], "Removed '{}' from the watchlist".format(titles["main"]["x-jat"][0]))
        
        @waterbug.expose(name="list")
        def list_(self, data, server, *args):
            hasitems = False
            for aid, info in self.watchedtitles.items():
                if (server.connection_name, data["target"]) in info:
                    server.notice(data["sender"].username, "{} [{}]".format(
                                                                self.titles[aid]["main"]["x-jat"][0],
                                                                info[(server.connection_name, data["target"])]))
                    hasitems = True
            
            if not hasitems:
                server.msg(data["target"], "You are not following any animes")
        
    anidb = waterbug.expose()(AnidbCommands())
    