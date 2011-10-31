
def reduce_until(function, iterable, initializer, condition=lambda x, y: True):
    a = initializer
    iterator = iter(iterable)
    prev = []
    for i in iterator:
        if not condition(a, i):
            prev = [i]
            break
        a = function(a, i)
    
    return (a, prev + list(iterator))


def all_in(a, b):
            for i in a:
                if i not in b:
                    return False
            
            return True