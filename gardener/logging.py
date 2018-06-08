class Icons:
    Sparkle = u"\u2728"
    Recycle = u"\U0001F4CC"
    Error = u"\u26D4"
    Check = u"\u2705"

def log(msg, icon=""):
    print(icon + "  " + msg)


def logInfo(msg):
    log(msg)


def logSuccess(msg):
    log(msg, Icons.Check)


def logError(msg):
    log(msg, Icons.Error)


def logCreate(msg):
    log(msg, Icons.Sparkle)


def logRecycle(msg):
    log(msg, Icons.Recycle)


def logDebug(msg):
    # if DEBUG:
    print(msg)