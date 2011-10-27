import logging
import sys

import waterbug.waterbug as waterbug

def main(*argv):
    
    logging.basicConfig(format="%(asctime)s %(message)s", datefmt="[%H:%M:%S]", level=logging.INFO, stream=sys.stdout)
    
    bot = waterbug.Waterbug()
    bot.load_modules()
    bot.open_connections()

if __name__ == "__main__":
    main(*sys.argv)
