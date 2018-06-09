import json

class Config:
    """
    Represent the Gardener configuration.Can be created programmatically via the accessory methods
    or it can be loaded from a json config file
    """
    Cores = {}
    Group = {}
    Things = {}
    Region = ''
    Lambdas = {}
    Routes = []
    Loggers = []
    Policies = {}

    def __init__(self, file=None):
        if file is None:
            return

        with open(file) as f:
            dictionary = json.load(f)

        for k, v in dictionary.items():
            setattr(self, k, v)

    def load(self, file):
        with open(file) as f:
            dictionary = json.load(f)

        for k, v in dictionary.items():
            setattr(self, k, v)

    def addCore(self, id=None, name=None, syncShadow=None, policy=None):
        if len(self.Cores) > 0:
            raise ValueError("Too many cores")
        if policy not in self.Policies.keys():
            raise ValueError("Policy not found")
        self.Cores[id] = {
            "name": name,
            "syncShadow": syncShadow,
            "policy": policy
        }

    def addGroup(self, name=None, roleArn=None, deploy=False):
        self.Group = {
            "name": name,
            "roleArn": roleArn,
            "deploy": deploy
        }
    
    def addThing(self, id=None, name=None, syncShadow=False, policy=None):
        if policy not in self.Policies.keys():
            raise ValueError("Policy not found")
        self.Things[id] = {
            "name": name,
            "syncShadow": syncShadow,
            "policy": policy
        }
    
    def addLambda(self, id=None, arn=None, functionConfiguration=None):
        self.Lambdas[id] = {
            "arn": arn,
            "FunctionConfiguration": functionConfiguration
        }

    def addRoute(self, source=None, subject=None, target=None):
        things = ['thing:'+x for x in self.Things.keys()]
        lambdas = ['lambda:'+x for x in self.Lambdas.keys()]
        if source not in things+lambdas+['GGShadowService', 'cloud']:
            raise ValueError('Source not defined')
        if target not in things+lambdas+['GGShadowService', 'cloud']:
            raise ValueError('Target not defined')
        if subject.startswith('shadow') and subject.split(':')[1] not in self.Things.keys():
            raise ValueError('Shadow not defined')
        self.Routes.append({
            "Source": source,
            "Subject": subject,
            "Target": target
        })
    
    def addGreengrassSystemLogger(self, level=None, space=None, logtype=None ):
        self.Loggers = [x for x in self.Loggers if x["Component"] != "GreengrassSystem"].append({
            "Component": "GreengrassSystem",
            "Level": level,
            "Space": space,
            "Type": logtype
        })

    def addLambdaLogger(self, level=None, space=None, logtype=None ):
        self.Loggers = [x for x in self.Loggers if x["Component"] != "Lambda"].append({
            "Component": "Lambda",
            "Level": level,
            "Space": space,
            "Type": logtype
        })

    def addPolicy(self, id=None, policy=None):
        self.Policies[id] = policy