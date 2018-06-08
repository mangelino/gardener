import json

class Config:
    """
    This class is created dynamically based the json file which is passed to it
    """
    Cores = {}
    Group = {}
    Things = {}
    Region = ''
    Lambdas = {}
    Routes = []
    Loggers = []
    Policies = {}

    def __init__(self, file):
        with open(file) as f:
            dictionary = json.load(f)

        for k, v in dictionary.items():
            setattr(self, k, v)



