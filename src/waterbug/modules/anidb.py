
import pprint
import gzip
import urllib.request
import xml.etree.ElementTree as ElementTree

import waterbug.util as wutil
import waterbug.waterbug as waterbug

class Commands:
    
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
                    info["similaranime"].append({"aid": int(anime.attrib['id']), "approval": int(anime.attrib['approval']),
                                                 "total": int(anime.attrib['total']), "title": anime.text,
                                                 "percentage": round(100*int(anime.attrib['approval'])/int(anime.attrib['total']), 2)})
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
        def add(self, data, server, *args):
            server.msg(data["target"], "adding: {}".format(data['line']))
        
        @waterbug.expose()
        def remove(self, data, server, *args):
            server.msg(data["target"], "removing: {}".format(data['line']))
        
        @waterbug.expose()
        def search(self, data, server, *args):
            r = self._search(data['line'], limit=4)
            for aid, titles in r.items():
                server.msg(data["target"], "{} - http://anidb.net/a{}".format(
                                                                self.format_title(titles), aid))
            if len(r) == 0:
                server.msg(data["target"], "No anime found")
        
    anidb = waterbug.expose()(AnidbCommands())
    