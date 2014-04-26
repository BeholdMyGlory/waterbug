
import sys
import traceback

try:
    exec compile(raw_input(), '<string>', 'single')
except Exception as e:
    etype, evalue, _ = sys.exc_info()
    print(traceback.format_exception_only(etype, evalue)[-1])
