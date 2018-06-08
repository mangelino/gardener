import json

def jsonPP(j):
    print(json.dumps(j, indent=2))

def dicSlice(d, keys):
    return dict((k, d[k]) for k in keys if k in d)

def hashDict(d, ignore=[]):
        """
        Creates an hash/uuid of a dictionary ignoring specific keys
        TODO: Bundle this in a util package
        """
        s = ""
        keys = list(d.keys())
        keys.sort()
        for k in keys:
            if not k in ignore:
                s += str(k)+str(d[k])
        return s

def compareDict(a, b):
    """
    Compare two definitions removing the unique Ids from the entities
    """
    ignore = ['Id']
    _a = [hashDict(dict(x), ignore) for x in a]
    _b = [hashDict(dict(y), ignore) for y in b]
    _a.sort()
    _b.sort()
    
    return _a == _b