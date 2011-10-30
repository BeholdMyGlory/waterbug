
import pprint
import xml.etree.ElementTree as ElementTree

import waterbug.waterbug as waterbug

class Commands:
    
    class AnidbCommands:
        
#        class TitleHandler(xml.sax.handler.ContentHandler):
#            
#            def __init__(self):
#                super().__init__()
#                self.titles = {}
#                self.currenttitle = None
#            
#            def startElement(self, name, attrs):
#                if name == "anime":
#                    self.currentanime = {}
#                    self.titles[int(attrs.getValue("aid"))] = self.currentanime
#                elif name == "title":
#                    self.currenttitle = {"type": attrs.getValue("type"),
#                                         "lang": attrs.getValue("xml:lang")}
#            
#            def endElement(self, name):
#                if name == "title":
#                    self.currenttitle = None
#            
#            def characters(self, content):
#                if self.currenttitle is not None:
#                    if self.currenttitle["type"] not in self.currentanime:
#                        self.currentanime[self.currenttitle["type"]] = {}
#                    if self.currenttitle["lang"] not in self.currentanime[self.currenttitle["type"]]:
#                        self.currentanime[self.currenttitle["type"]][self.currenttitle["lang"]] = []
#                    self.currentanime[self.currenttitle["type"]][self.currenttitle["lang"]] \
#                                                    .append(content.strip())
        
        
        def __init__(self):
            self.titles = {}
            for (event, elem) in ElementTree.iterparse(open("animetitles.xml"), ("start", "end")):
                if event == "start" and elem.tag == "anime":
                    currentanime = {}
                    self.titles[int(elem.attrib['aid'])] = currentanime
                if event == "end" and elem.tag == "title":
                    if elem.attrib['type'] not in currentanime:
                        currentanime[elem.attrib['type']] = {}
                    if elem.attrib['{http://www.w3.org/XML/1998/namespace}lang'] not in currentanime[elem.attrib['type']]:
                        currentanime[elem.attrib['type']][elem.attrib['{http://www.w3.org/XML/1998/namespace}lang']] = []
                    currentanime[elem.attrib['type']][elem.attrib['{http://www.w3.org/XML/1998/namespace}lang']].append(elem.text)
        
        def all_in(self, a, b):
            for i in a:
                if i not in b:
                    return False
            
            return True
        
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
                            if self.all_in(keywords, title):
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
            server.msg(data["target"], "{} - http://anidb.net/a{}".format(
                                                            self.format_title(titles), aid))
        
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
    