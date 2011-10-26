
import builtins

import waterbug.waterbug as waterbug

class Commands:
    
    def __init__(self):
        self.g_context = {"__builtins__": {x: getattr(builtins, x)
                                           for x in ["abs", "all", "any", "ascii", "bin",
                                                     "bool", "bytearray", "bytes", "callable",
                                                     "chr", "classmethod", "complex",
                                                     "delattr", "dict", "dir", "divmod",
                                                     "enumerate", "filter", "float",
                                                     "format", "frozenset", "getattr",
                                                     "globals", "hasattr", "hash", "help",
                                                     "hex", "id", "int", "isinstance",
                                                     "issubclass", "iter", "len", "list",
                                                     "locals", "map", "max", "memoryview",
                                                     "min", "next", "object", "oct",
                                                     "ord", "pow", "property", "range",
                                                     "repr", "reversed", "round", "set",
                                                     "setattr", "slice", "sorted",
                                                     "staticmethod", "str", "sum", "super",
                                                     "tuple", "type", "vars", "zip"]}}
        def _import(*args):
            if args[0] in ["math"]:
                return __import__(*args)
            else:
                raise ImportError("No module named " + args[0])
        self.g_context['__builtins__']['__import__'] = _import
        self.l_context = {}
    
    @waterbug.expose()
    def echo(self, data, server, *args):
        """Echoes back the written line"""
        server.msg(data["target"], data["line"])
    
    @waterbug.expose(access=waterbug.ADMIN)
    def join(self, data, server, channel=None, *args):
        print(repr(channel))
        if channel is None:
            server.msg(data["target"], "You need to supply a channel to join")
        else:
            server.msg(data["target"], "Joining {}".format(channel))
            server.join(channel)
    
    @waterbug.expose(access=waterbug.ADMIN)
    def part(self, data, server, channel=None, *args):
        if channel is None:
            server.msg(data["target"], "Parting...")
            server.part(data["target"])
        else:
            server.msg(data["target"], "Parting {}...".format(channel))
            server.part(channel)
    
    @waterbug.expose(name="quit", access=waterbug.ADMIN)
    def quit_(self, data, server, *args):
        server.msg(data["target"], "Quitting...")
        for server in self.bot.servers.values():
            server.write("QUIT :buh-buh")
    
    @waterbug.expose()
    def py(self, data, server, *args):
        server.msg(data["target"], repr(eval(data["line"], self.g_context, self.l_context)))
    
    @waterbug.expose()
    def pyexec(self, data, server, *args):
        exec(data["line"], self.g_context, self.l_context)
        server.msg(data["target"], "Execution finished")
