import asyncore
import imp
import importlib
import inspect
import logging
import pkgutil
import shelve
import sys
import threading
import traceback

import waterbug.network
import waterbug.modules
import waterbug.util

BANNED = 0
STANDARD = 1
TRUSTED = 2
ELEVATED = 3
OP = 4
ADMIN = 5

class Waterbug:
    
    def __init__(self, prefix='%'):
        self.servers = {}
        self.commands = {}
        self.modules = []
        self.prefix = prefix
        
        self.data = shelve.open("storage/data.pck")
        
        self.config = {
            "waterbug": {
                "prefix": "%"
            },
            "servers": {
                "FreeNode": {
                    "hostname": "chat.freenode.net",
                    "port": 6667,
                    "autojoin": ["##FireFly", "##tullinge"],
                    "privileges": {
                        "unaffiliated/beholdmyglory": ADMIN
                    }
                }
            },
            "modules": {
                "anidb": {
                    "server": "api.anidb.net",
                    "port": 9001,
                    "protoversion": 1,
                    "clientname": "eldishttp",
                    "clientversion": 1
                }
            }
        }
        
        self.privileges = {
            "unaffiliated/beholdmyglory": ADMIN,
            
        }
        
        self.servers["FreeNode"] = waterbug.network.Server("irc.freenode.net", 6667, "FreeNode", self)
    
    def open_connections(self):
        for name, server in self.servers.items():
            logging.info("Connecting to %s (%s)", name, server.server_address[0])
            server.connect()
        
        thread = threading.Thread()
        thread.run = lambda: asyncore.loop()
        thread.start()
        
        self.servers["FreeNode"].join("##FireFly")
    
    def unload_modules(self):
        for module in self.modules:
            if hasattr(module.commands, "unload"):
                if getattr(module.commands.unload, "trigger", False):
                    module.commands.unload()
    
    def load_modules(self):
        self.commands = {}
        
        self.unload_modules()
        
        modules_to_reload = self.modules
        self.modules = []
        
        for module in modules_to_reload:
            try:
                logging.info("Reloading %s", module.__name__)
                self.modules.append(imp.reload(module))
            except BaseException:
                traceback.print_exc()
        
        for _, module_name, _ in pkgutil.iter_modules(waterbug.modules.__path__,
                                                      "waterbug.modules."):
            try:
                logging.info("Loading %s", module_name)
                if module_name not in sys.modules:
                    self.modules.append(importlib.import_module(module_name))
            except BaseException:
                traceback.print_exc()
        
        for module in self.modules:
            try:
                
                module_data = Waterbug.ModuleStorage(module.__name__, self.data)
                
                def add_commands(cobj, clist):
                    cobj.bot = self
                    cobj.data = module_data
                    if hasattr(cobj, "init") and getattr(cobj.init, "trigger", False):
                        cobj.init()
                    for name, value in inspect.getmembers(cobj):
                        if getattr(value, "exposed", False):
                            if callable(value):
                                clist[value.__name__] = value
                            else:
                                clist[name] = {}
                                add_commands(value, clist[name])
                
                
                module.commands = module.Commands()
                add_commands(module.commands, self.commands)
            
            except BaseException:
                traceback.print_exc()
    
    class ModuleStorage:
        
        def __init__(self, name, data):
            self.name = name
            if name not in data:
                data[name] = {}
            self.data = data[name]
            self._data = data
        
        def sync(self):
            self._data[self.name] = self.data
            self._data.sync()
        
        def get_data(self):
            return self.data
    
    
    def on_privmsg(self, server, sender, receiver, message):
        if receiver[0] in server.supported['CHANTYPES']:
            target = receiver
        else:
            target = sender
        if message.startswith(self.prefix):
            message = message[1:]
            command, args = waterbug.util.reduce_until(lambda x, y: x[y], message.split(" "), self.commands,
                                                       lambda x, y: type(x) is dict and y in x)
            
            if callable(command):
                func = command
            elif type(command) is dict and "_default" in command and callable(command["_default"]):
                func = command["_default"]
            else:
                return
            
            if sender.access >= func.access:
                try:
                    func({"command": command, "sender": sender, "target": target,
                          "receiver": receiver, "line": " ".join(args)}, server, *args)
                except BaseException:
                    traceback.print_exc()
                    exc_type, exc_value, exc_traceback = sys.exc_info()
                    exc = traceback.format_exception_only(exc_type, exc_value)
                    stack = traceback.format_tb(exc_traceback)
                    exception = "{}: {}".format(stack[-1], "".join(exc)).replace("\n", "")
                    server.msg(target, exception)
            else:
                server.msg(target, "You do not have access to this command")

def expose(name=None, access=STANDARD):
    def decorator(target):
        target.exposed = True
        target.access = access
        if name is not None:
            target.__name__ = name
        if target.__doc__ is None:
            target.__doc__ = "No help available for this command"
        return target
    return decorator

def trigger(target):
    target.trigger = True
    return target

