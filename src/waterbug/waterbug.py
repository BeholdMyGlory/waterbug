import asyncore
import imp
import importlib
import inspect
import logging
import pkgutil
import sys
import threading
import traceback

import waterbug.network
import waterbug.modules

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
        self.servers["FreeNode"].join("###sandbox")
    
    def load_modules(self):
        self.commands = {}
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
                
                def add_commands(cobj, clist):
                    cobj.bot = self
                    for name, value in inspect.getmembers(cobj):
                        if getattr(value, "exposed", False):
                            if callable(value):
                                clist[value.__name__] = value
                            else:
                                clist[name] = {}
                                add_commands(value, clist[name])
                
                add_commands(module.Commands(), self.commands)
            
            except BaseException:
                traceback.print_exc()
    
    def on_privmsg(self, server, sender, receiver, message):
        if receiver[0] in server.supported['CHANTYPES']:
            target = receiver
        else:
            target = sender
        if message.startswith(self.prefix):
            message = message[1:]
            def run_command(string, clist):
                (command, *string) = string.split(' ', 1)
                string = '' if len(string) == 0 else string[0]
                
                if command in clist:
                    if callable(clist[command]):
                        func = clist[command]
                    else:
                        run_command(string, clist[command])
                        return
                elif "_default" in clist:
                    string = command + (" " + string if len(string) > 0 else '')
                    command = "_default"
                    func = clist['_default']
                else:
                    return
                
                if sender.access >= func.access:
                    try:
                        func({"command": command, "sender": sender, "target": target,
                              "receiver": receiver, "line": string}, server,
                             *([] if len(string) == 0 else string.split(' ')))
                    except BaseException:
                        traceback.print_exc()
                        exc_type, exc_value, exc_traceback = sys.exc_info()
                        exc = traceback.format_exception_only(exc_type, exc_value)
                        stack = traceback.format_tb(exc_traceback)
                        exception = "{}: {}".format(stack[-1], "".join(exc)).replace("\n", "")
                        server.msg(target, exception)
                else:
                    server.msg(target, "You do not have access to this command")
                
            run_command(message, self.commands)

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
