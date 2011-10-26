
import collections
import functools
import itertools

import waterbug.waterbug as waterbug

class Commands:
    
    @waterbug.expose(name="eval", access=waterbug.ADMIN)
    def eval_(self, data, server, *args):
        """Evaluates a Python expression in an unrestricted context"""
        server.msg(data["target"], repr(eval(data["line"])))
    
    @waterbug.expose(access=waterbug.ADMIN)
    def reload(self, data, server, *args):
        """Reloads all modules"""
        self.bot.load_modules()
        server.msg(data["target"], "Modules reloaded successfully")
    
    @waterbug.expose(name="help")
    def help_(self, data, server, *args):
        """Displays help for the specified command"""
        try:
            command = functools.reduce(lambda x, y: x[y], args, self.bot.commands)
            if callable(command):
                server.msg(data["target"], command.__doc__)
            else:
                server.msg(data["target"], command["_default"].__doc__)
        except KeyError:
            server.msg(data["target"], "No such command")
    
    @waterbug.expose()
    def commands(self, data, server, *args):
        """Displays all available commands"""
        def flatten_dict(d):
            items = d.items()
            queue = collections.deque(zip(itertools.repeat(()), (x[0] for x in items),
                                          (x[1] for x in items)))
            result = []
            while len(queue) > 0:
                (depth, key, value) = queue.popleft()
                if type(value) is dict:
                    items = value.items()
                    queue.extend(zip(itertools.repeat(depth + (key,)), (x[0] for x in items),
                                     (x[1] for x in items)))
                else:
                    if key != "_default":
                        depth += (key,)
                    result.append((' '.join(depth), value))
            return result
        
        comm = flatten_dict(self.bot.commands)
        comm = sorted([x[0] for x in comm if data["sender"].access >= x[1].access])
        server.msg(data["target"], "Available commands: " + ', '.join(comm))
    
    @waterbug.expose()
    def whoami(self, data, server, *args):
        """Displays your information such as username, hostname and access level"""
        server.msg(data["target"], "You are {}!{}@{}, and you have access {}"
                   .format(data["sender"].username, data["sender"].ident, data["sender"].hostname,
                           data["sender"].access))
    
    @waterbug.expose(access=waterbug.ADMIN)
    def access(self, data, server, *args):
        try:
            (user, access_name) = args
        except ValueError:
            server.msg(data["target"], "Invalid number of parameters")
            return
        
        access_value = getattr(waterbug, access_name, None)
        if type(access_value) is not int:
            server.msg(data["target"], "Invalid access type")
            return
        
        self.bot.privileges[user] = access_value
        server.msg(data["target"], "User {} is now {}".format(user, access_name))
    
