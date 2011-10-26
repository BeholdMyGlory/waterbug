
import waterbug.waterbug as waterbug

class Commands:
    
    class AnidbCommands:
        
        @waterbug.expose()
        def add(self, data, server, *args):
            server.msg(data["target"], "adding: {}".format(data['line']))
        
        @waterbug.expose()
        def remove(self, data, server, *args):
            server.msg(data["target"], "removing: {}".format(data['line']))
        
        @waterbug.expose()
        def _default(self, data, server, *args):
            server.msg(data["target"], "DEFAULT: {}".format(data['line']))
        
    anidb = waterbug.expose()(AnidbCommands())
    