#!/usr/local/bin/python
import json
import boto3
from itertools import chain
import uuid
import re
import sys
import argparse
from collections import OrderedDict
from gg_config import Config

DEBUG = False


class Icons:
    Sparkle = u"\u2728"
    Recycle = u"\U0001F4CC"
    Error = u"\u26D4"
    Check = u"\u2705"


def jsonPP(j):
    print(json.dumps(j, indent=2))

def dicSlice(d, keys):
    return dict((k, d[k]) for k in keys if k in d)


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
    if DEBUG:
        print(msg)

class Thing():

    def __init__(self, config):
        self.config = config
        self.iot = boto3.client('iot', region_name=self.config.Region)
        self.entityName = "thing"

    def dumpKeys(self, cert, privkey):
        print('Certificate PEM')
        print(cert)
        print('PrivateKey')
        print(privkey)

    def createThing(self, name, policy):
        res = self.iot.create_thing(thingName=name)
        thingArn = res['thingArn']
        res = self.iot.list_thing_principals(thingName=name)
        principals = res['principals']
        logDebug(principals)
        if not policy in self.config.Policies:
            logError('Missing policy {0} from configuration'.format(policy))
        policyDoc = self.config.Policies[policy]
        
        if len(principals) > 1:
            logError(
                'Thing should only have 1 certificate. Not possible to continue')
            return False
        elif len(principals) == 1:
            certArn = res['principals'][0]
            self._createOrUpdatePolicy(policy, policyDoc)
            logRecycle('Using exisiting thing')
        else:
            res = self.iot.create_keys_and_certificate(setAsActive=True)
            certArn = res['certificateArn']
            logSuccess('Certificate {0}'.format(certArn))
            self.dumpKeys(res['certificatePem'], res['keyPair']['PrivateKey'])

            self._createOrUpdatePolicy(policy, policyDoc)

            res = self.iot.attach_principal_policy(
                policyName=policy + "_Policy", principal=certArn)
            logInfo('Attached policy to certificate')
            res = self.iot.attach_thing_principal(
                thingName=name, principal=certArn)
            logInfo('Attached certificate to thing')
        return {'thingArn': thingArn, 'certArn': certArn}


    def getThingDefinition(self, things):
        return [
            {
                "ThingArn": t['thingArn'],
                "SyncShadow":t['syncShadow'],
                "CertificateArn":t['certArn'],
                "Id":str(uuid.uuid4())
            }
            for t in things]

    def _createOrUpdatePolicy(self, policyName, policyDoc):
        policies = dict([(x['policyName'], x['policyArn']) for x in self.iot.list_policies()['policies']])

        if policyName + '_Policy' in policies.keys():
            currentPolicyDoc = self.iot.get_policy(policyName=policyName + '_Policy')['policyDocument']
            #logInfo(currentPolicyDoc)
            if policyDoc == json.loads(currentPolicyDoc):
                logInfo('Policies are identical')
            # Should check if policies are identical
            logRecycle('Policy {0} already exists with arn {1}'.format(
                policyName + '_Policy', policies[policyName + '_Policy']))
        else:
            res = self.iot.create_policy(
                policyName=policyName + "_Policy", policyDocument=json.dumps(policyDoc))
            logSuccess('Created policy {0}'.format(res['policyArn']))
        return policyName

class EntityDefinition: 
    def __init__(self, gg, config):
        self.gg = gg
        self.entityName = "entity"
        self.config = config

    def getPostfix(self):
        return ""

    def getExistingDefinitions(self):
        return []

    def getEntityVersion(self, defId, verId):
        return None

    def getModelDefinition(self):
        return {}

    def createEntityDefinition(self, name):
        return {'Id':None}

    def createEntityDefinitionVersion(self, defId, model):
        return {'Arn':None}
    
    def hashDict(self, d, ignore=[]):
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

    def compareDefinitions(self, a, b):
        """
        Compare two definitions removing the unique Ids from the entities
        """
        ignore = ['Id']
        _a = [self.hashDict(dict(x), ignore) for x in a]
        _b = [self.hashDict(dict(y), ignore) for y in b]
        _a.sort()
        _b.sort()
        
        return _a == _b

    def create(self):
        version = []
        #print(self.entityName)
        name = self.config.Group['name']+self.getPostfix()
        definitions = [dicSlice(x, ['Id', 'LatestVersion', 'LatestVersionArn']) for x in self.getExistingDefinitions() if 'Name' in x and x['Name']==name]
        if len(definitions)>1:
            logError('More than 1 {0} with name {1} exists'.format(self.entityName, name))
            return False
        elif len(definitions) == 1:
            entityDefinitionId = definitions[0]['Id']
            if 'LatestVersion' in definitions[0]:
            #logRecycle('Core with name {0} aready exists with id {1}. Reusing it.'.format(name, coreDefinitionId))
                version = self.getEntityVersion(entityDefinitionId, definitions[0]['LatestVersion'])
        else:
            res = self.createEntityDefinition(name)
            entityDefinitionId = res['Id']
            logInfo('Created {0} definition {1}'.format(self.entityName, entityDefinitionId))
        
        try:
            modelDefinition = self.getModelDefinition()
        except NameError as e:
            logError(e)
            return False
        if len(version) and self.compareDefinitions(version, modelDefinition):
            logRecycle('{0} version has not changed'.format(self.entityName))
            self.arn = definitions[0]['LatestVersionArn']
        else:
            res = self.createEntityDefinitionVersion(entityDefinitionId, modelDefinition)
            self.arn = res['Arn']
            logSuccess('Created {0} definition version {1}'.format(self.entityName, self.arn))
        return True



class CoreDefinition(EntityDefinition):
    """
    Create a new Core definition if it does not already exists.
    Compare LatestVersion with new model configuration to avoid creating identical versions
    """
    def __init__(self, gg, config):
        EntityDefinition.__init__(self, gg, config)
        self.entityName = "core"

    def getPostfix(self):
        return "_core_definition"

    def getModelDefinition(self):
        coreKey = list(self.config.Cores.keys())[0]
        thing = Thing(self.config)
        ggCoreThing = thing.createThing(self.config.Cores[coreKey]['name'], self.config.Cores[coreKey]['policy'])
        things = [dict(chain(ggCoreThing.items(), v.items(), {'id': k}.items())) for k,v in self.config.Cores.items()]
        return thing.getThingDefinition(things)

    def getExistingDefinitions(self):
        return self.gg.list_core_definitions()['Definitions']

    def createEntityDefinition(self, name):
        return self.gg.create_core_definition(Name=name)

    def getEntityVersion(self, defId, verId):
        ver = self.gg.get_core_definition_version(CoreDefinitionId=defId, CoreDefinitionVersionId=verId)
        return ver['Definition']['Cores']

    def createEntityDefinitionVersion(self, defId, model):
        return self.gg.create_core_definition_version(CoreDefinitionId=defId, Cores=model)

class DeviceDefinition(EntityDefinition):
    """
    Create a new Device definition if it does not already exists.
    Compare LatestVersion with new model configuration to avoid creating identical versions
    """
    def __init__(self, gg, config):
        EntityDefinition.__init__(self, gg, config)
        self.entityName = "device"
        self.things = []

    def getPostfix(self):
        return "_device_defintion"

    def getModelDefinition(self):
        thing = Thing(self.config)
        self.things = [dict(
                    chain(
                        thing.createThing(v['name'], v['policy']).items(), 
                        v.items(), 
                        {'id': k}.items()
                    )
                ) for k,v in self.config.Things.items()]

        return thing.getThingDefinition(self.things)

    def getExistingDefinitions(self):
        return self.gg.list_device_definitions()['Definitions']

    def createEntityDefinition(self, name):
        return self.gg.create_device_definition(Name=name)

    def getEntityVersion(self, defId, verId):
        ver = self.gg.get_device_definition_version(DeviceDefinitionId=defId, DeviceDefinitionVersionId=verId)
        return ver['Definition']['Devices']

    def createEntityDefinitionVersion(self, defId, model):
        return self.gg.create_device_definition_version(DeviceDefinitionId=defId, Devices=model)  

class FunctionDefinition(EntityDefinition):

    def __init__(self, gg,config):
        EntityDefinition.__init__(self, gg, config)
        self.entityName = "function"

    def getPostfix(self):
        return "_function_definition"

    def getModelDefinition(self):
        return [
            {
                "FunctionArn": v['arn'],
                "Id":str(uuid.uuid4()),
                "FunctionConfiguration": v['FunctionConfiguration']
            }
            for k, v in self.config.Lambdas.items()]
    
    def getExistingDefinitions(self):
        return self.gg.list_function_definitions()['Definitions']

    def createEntityDefinition(self, name):
        return self.gg.create_function_definition(Name=name)

    def getEntityVersion(self, defId, verId):
        ver = self.gg.get_function_definition_version(FunctionDefinitionId=defId, FunctionDefinitionVersionId=verId)
        return ver['Definition']['Functions']

    def createEntityDefinitionVersion(self, defId, model):
        return self.gg.create_function_definition_version(FunctionDefinitionId=defId, Functions=model)

class SubscriptionDefinition(EntityDefinition):
    _thingRegex = re.compile(r'thing:(?P<thing>\w+)')
    _shadowRegex = re.compile(r'shadow:(?P<thing>\w+):(?P<op>[\w/]+)')
    _lambdaRegex = re.compile(r'lambda:(?P<lambda>\w+)')

    def __init__(self, gg, config, devices):
        EntityDefinition.__init__(self, gg, config)
        self.entityName = "subscription"
        self.devices = devices

    def getPostfix(self):
        return "_subscription_definition"

    def getModelDefinition(self):
        return self._getSubscriptionModel(self.config.Routes, self.devices.things, self.config.Lambdas)
            
    def getExistingDefinitions(self):
        return self.gg.list_subscription_definitions()['Definitions']

    def createEntityDefinition(self, name):
        return self.gg.create_subscription_definition(Name=name)

    def getEntityVersion(self, defId, verId):
        ver = self.gg.get_subscription_definition_version(SubscriptionDefinitionId=defId, SubscriptionDefinitionVersionId=verId)        
        return ver['Definition']['Subscriptions']

    def createEntityDefinitionVersion(self, defId, model):
        return self.gg.create_subscription_definition_version(SubscriptionDefinitionId = defId, Subscriptions = model)

    def _getSubscriptionModel(self, subs, things, lambdas):
        """
        Return the sucbscription model based on the configuration and the dynamically generated ARNs of the Devices and Functions

        Parameters:
            subs: the Subscriptions model from the Config file, a list of dictionaries specifying source, target, and subject
            [
                {
                    "Source": "",
                    "Target": "",
                    "Subject: ""
                },

            ]

            things: the list of things things in this configuration
            lambdas: the list of lambdas in this configuration
        """
        def _getThingArn(id):
            for t in things:
                if t['id'] == id:
                    return t['thingArn']
            raise NameError("Thing {0} not found".format(id))

        def _getLambdaArn(id):
            for k, v in lambdas.items():
                if k == id:
                    return v['arn']
            raise NameError("Lambda {0} not found".format(id))

        def _checkThing(d, element):
            # print ('Thing'+str(d))
            m = self._thingRegex.match(d[element])
            if m:
                d[element] = _getThingArn(m.group('thing'))

        def _checkLambda(d, element):
            # print ('Lambda'+str(d))
            m = self._lambdaRegex.match(d[element])
            if m:
                d[element] = _getLambdaArn(m.group('lambda'))

        def _getThingName(id):
            for t in things:
                if t['id'] == id:
                    return t['name']

        def _checkSubject(d):
            # print('Subject'+str(d))
            m = self._shadowRegex.match(d['Subject'])
            if m:
                d['Subject'] = '$aws/things/{0}/shadow{1}'.format(
                    _getThingName(m.group('thing')), m.group('op'))

        def _buildSubscriptionElement(d):
            _checkThing(d, 'Source')
            _checkThing(d, 'Target')
            _checkLambda(d, 'Source')
            _checkLambda(d, 'Target')
            _checkSubject(d)
            return dict(chain(d.items(), {"Id": str(uuid.uuid4())}.items()))

        return [_buildSubscriptionElement(m) for m in subs]

class LoggerDefinition(EntityDefinition):

    def __init__(self, gg,config):
        EntityDefinition.__init__(self, gg, config)
        self.entityName = "logger"

    def getPostfix(self):
        return "_logger_definition"

    def getModelDefinition(self):
        return [
            {
                "Component": l['Component'],
                "Id": str(uuid.uuid4()),
                "Level": l['Level'],
                "Space": l['Space'],
                "Type": l['Type']
            }
            for l in self.config.Loggers]

    def getExistingDefinitions(self):
        return self.gg.list_logger_definitions()['Definitions']

    def createEntityDefinition(self, name):
        return self.gg.create_logger_definition(Name=name)

    def getEntityVersion(self, defId, verId):
        ver = self.gg.get_logger_definition_version(LoggerDefinitionId=defId, LoggerDefinitionVersionId=verId)
        return ver['Definition']['Loggers']

    def createEntityDefinitionVersion(self, defId, model):
        return self.gg.create_logger_definition_version(LoggerDefinitionId=defId, Loggers=model)


class Gardener:

    def __init__(self, configfile='config.json'):
        self.config = Config(configfile)
        self.gg = boto3.client('greengrass', region_name=self.config.Region)
        # self.iot = boto3.client('iot', region_name=self.config.Region)

    def compareGroupVersion(self, gdv):
        logRecycle("""--core-definition-version-arn {0}
        --device-definition-version-arn {1}
        --function-definition-version-arn {2}
        --logger-definition-version-arn {3}
        --subscription-definition-version-arn {4}""".format(self.core.arn,self.devices.arn,self.functions.arn,self.loggers.arn,self.subscriptions.arn))
        return (gdv['CoreDefinitionVersionArn'] == self.core.arn and
            gdv['DeviceDefinitionVersionArn'] == self.devices.arn and
            gdv['FunctionDefinitionVersionArn'] == self.functions.arn and
            gdv['LoggerDefinitionVersionArn'] == self.loggers.arn and
            gdv['SubscriptionDefinitionVersionArn'] == self.subscriptions.arn)

    def _createGGGroup(self):
        gv = []
        groups = [dicSlice(x,['Id', 'LatestVersion']) for x in self.gg.list_groups()['Groups'] if 'Name' in x and x['Name']==self.config.Group['name']]
        if len(groups)>1:
            logError('More than 1 group with same name {0} already exists. Rename or delete other groups to continue.'.format(self.config.Group['name']))
            return False
        elif len(groups) == 1:
            self.groupId = groups[0]['Id']
            # logRecycle ('Group {0} already exists with id {1}. Updating it'.format(self.config.Group['name'], self.groupId))
            if 'LatestVersion' in groups[0]:
                gv = self.gg.get_group_version(GroupId=self.groupId, GroupVersionId=groups[0]['LatestVersion'])
        else:
            res = self.gg.create_group(Name=self.config.Group['name'])
            self.groupId = res['Id']
            logSuccess('Created group {0} with id {1}'.format(self.config.Group['name'], self.groupId))
        
        try:
            res = self.gg.list_group_certificate_authorities(GroupId=self.groupId)
            if len(res['GroupCertificateAuthorities'])==0:
                logInfo('Create Group Certificate Authority')
                res = self.gg.create_group_certificate_authority(GroupId=self.groupId)
            else:
                logInfo('Group Certificate Authority already exists.')
        except Exception as e:
            logInfo(str(type(e))+str(e))
            logInfo('Create Group Certificate Authority')
            res = self.gg.create_group_certificate_authority(GroupId=self.groupId)
        
        res = self.gg.associate_role_to_group(GroupId=self.groupId, RoleArn=self.config.Group['roleArn'])
        logInfo('Role {0} associated to group'.format(self.config.Group['roleArn']))
        
        if len(gv)>0 and self.compareGroupVersion(gv['Definition']):
            self.groupVersion = groups[0]['LatestVersion']
            logRecycle('Group Version has not changed')
        else:
            res = self.gg.create_group_version(GroupId=self.groupId, CoreDefinitionVersionArn=self.core.arn, DeviceDefinitionVersionArn=self.devices.arn, 
            FunctionDefinitionVersionArn=self.functions.arn, LoggerDefinitionVersionArn=self.loggers.arn, SubscriptionDefinitionVersionArn=self.subscriptions.arn)
            self.groupVersion = res['Version']
            logSuccess('Created group version {0} {1}'.format(res['Arn'], res['Version']))       
        return True
    
    # def _createGGGroupWithCoreOnly(self):
    #     groups = [x['Id'] for x in self.gg.list_groups()['Groups'] if 'Name' in x and x['Name']==self.config.Group]
    #     if len(groups)>1:
    #         logError('More than 1 group with same name {0} already exists. Rename or delete other groups to continue.'.format(self.config.Group))
    #         return False
    #     elif len(groups) == 1:
    #         # logRecycle ('Group {0} already exists with id {1}. Updating it'.format(self.Config.Group, groups[0]))
    #         self.groupId = groups[0]
    #     else:
    #         res = self.gg.create_group(Name=self.config.Group['name'])
    #         self.groupId = res['Id']
    #         logSuccess('Created group {0} with id {1}'.format(self.config.Group['name'], self.groupId))
        
    #     res = self.gg.create_group_version(GroupId=self.groupId, CoreDefinitionVersionId=self.coreDefinitionArn)
    #     self.groupVersion = res['Version']
    #     logSuccess('Created group version {0} {1}'.format(res['Arn'], res['Version']))       
    #     return True
    
    def _createDeployment(self):
        res = self.gg.create_deployment(DeploymentType='NewDeployment', GroupId=self.groupId, GroupVersionId=self.groupVersion)
        res.pop('ResponseMetadata')
        logSuccess('Created deployment {0}'.format(res))
        return True

    def createGreengrass(self):
        self.core = CoreDefinition(self.gg, self.config)
        self.devices = DeviceDefinition(self.gg, self.config)
        self.functions = FunctionDefinition(self.gg, self.config)
        self.subscriptions = SubscriptionDefinition(self.gg, self.config, self.devices)
        self.loggers = LoggerDefinition(self.gg, self.config)

        if self.core.create() and self.devices.create() and self.functions.create() and self.loggers.create() and self.subscriptions.create() and self._createGGGroup():
            if self.config.Group['deploy']:
                if self._createDeployment():
                    print('\nExecute the following command on your Core')
                    print('''sudo sed -e 's/THING_ARN_HERE/{0}' /greengrass/configuration/config.json > /greengrass/configuration/config.json'''.format(self.core.arn.replace('/', '\/')))
                else:
                    print ('Something went wrong while deploying your Greengrass configuration')
            else:
                logSuccess('Greengrass has been configured but not deployed. Execute this command to deploy or use the console.')
                print('aws greengrass create-deployment --deployment-type "NewDeployment" --group-id {0} --group-version {1} --region {2}'.format(self.groupId, self.groupVersion, self.config.Region))
        else:
            print("Something went wrong while creating the Greengrass configuration")

    # def createGroupAndCore(self):
    #     self.core = CoreDefinition()
    #     if self.core.create() and self._createGGGroupWithCoreOnly():
    #         print('Greengrass Group and Core created')
    #     else:
    #         print("Something went wrong while creating the Greengrass configuration")
        
    def getLatestDeploymentStatus(self, groupName):
        res = self.gg.list_groups()
        group = [g for g in res['Groups'] if g['Name'] == groupName]
        if len(group) == 0:
            logError("No groups matching {0}".format(groupName))
            return False
        res = self.gg.list_deployments(GroupId=group[0]['Id'])
        deployments = res['Deployments']
        if len(deployments) == 0:
            logError("No deployments found for group {0}".format(groupName))
            return False
        deployments = sorted(deployments, key=lambda x: x["CreatedAt"], reverse=True)
        deploymentId = deployments[0]['Id']
        res = self.gg.get_deployment_status(DeploymentId = deploymentId, GroupId=group[0]['Id'])
        print("Latest deployment for group {0} is {1}".format(groupName, res['DeploymentStatus']))

    def getCurrentConfiguration(self, groupId=None):
        _regex = '.*{0}/(.*)/versions/(.*)'
        _name = '(\w+)DefinitionVersionArn'
        func = {
            'cores': lambda a, b : self.gg.get_core_definition_version(CoreDefinitionId = a, CoreDefinitionVersionId = b),
            'devices': lambda a, b : self.gg.get_device_definition_version(DeviceDefinitionId = a, DeviceDefinitionVersionId = b),
            'functions': lambda a, b : self.gg.get_function_definition_version(FunctionDefinitionId = a, FunctionDefinitionVersionId = b),
            'loggers': lambda a, b : self.gg.get_logger_definition_version(LoggerDefinitionId = a, LoggerDefinitionVersionId = b),
            'subscriptions': lambda a, b : self.gg.get_subscription_definition_version(SubscriptionDefinitionId = a, SubscriptionDefinitionVersionId = b)
        }
        groups = self.gg.list_groups()['Groups']
        if groupId is None:
            jsonPP(groups)
            return
        groupVersions = self.gg.list_group_versions(GroupId = groupId)['Versions']
        latestGroupVersion = groupVersions[0]
        groupDefinition = self.gg.get_group_version(GroupId = groupId, GroupVersionId = latestGroupVersion['Version'])['Definition']
        jsonPP(groupDefinition)
        for d in groupDefinition.keys():    
            _entity = re.match(_name, d)[1].lower()+'s'
            m = re.match(_regex.format(_entity), groupDefinition[d])
            jsonPP(func[_entity](m[1],m[2])['Definition'])
        return


    def cleanUpAll(self):
        groupIds = [x['Id'] for x in self.gg.list_groups()['DefinitionInformationDefinition']]
        coreDefinitionIds = [x['Id'] for x in self.gg.list_core_definitions()['DefinitionInformationDefinition']]
        deviceDefinitionIds = [x['Id'] for x in self.gg.list_device_definitions()['DefinitionInformationDefinition']]
        lambdaDefinitionIds = [x['Id'] for x in self.gg.list_lambda_definitions()['DefinitionInformationDefinition']]
        subscriptionDefinitionIds = [x['Id'] for x in self.gg.list_subscription_definitions()['DefinitionInformationDefinition']]
        loggingDefinitionIds = [x['Id'] for x in self.gg.list_logging_definitions()['DefinitionInformationDefinition']]
        print('Cleaning up groups...')
        for x in groupIds:
            try:
                print(x)
                self.gg.delete_group(GroupId=x)
            except:
                print('Unable to delete')
        print('Cleaning up cores...')
        for x in coreDefinitionIds:
            try:
                print(x)
                self.gg.delete_core_definition(CoreId=x)
            except:
                print('Unable to delete')
        print('Cleaning up devices...')
        for x in deviceDefinitionIds:
            try:
                print(x)
                self.gg.delete_device_definition(DeviceId=x)
            except:
                print('Unable to delete')
        print('Cleaning up lambdas...')
        for x in lambdaDefinitionIds:
            try:
                print(x)
                self.gg.delete_lambda_definition(LambdaId=x)
            except:
                print('Unable to delete')
        print('Cleaning up subscriptions...')
        for x in subscriptionDefinitionIds:
            try:
                print(x)
                self.gg.delete_subscription_definition(SubscritpionId=x)
            except:
                print('Unable to delete')
        print('Cleaning up logging...')
        for x in loggingDefinitionIds:
            try:
                print(x)
                self.gg.delete_logging_definition(LoggingId=x)
            except:
                print('Unable to delete')


        
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Greengrass Gardener')
    parser.add_argument('--config')
    subparsers = parser.add_subparsers(help='sub-command help', dest='subparser_name')

    parser_deploy = subparsers.add_parser('deploy', help='deploy help')
    parser_deploy.add_argument('--config')
    parser_ls = subparsers.add_parser('listGroups', help='listGroups help')
    parser_group = subparsers.add_parser('describeGroup', help='describeGroup help')
    parser_group.add_argument('--id')

    args = parser.parse_args()
    if args.config:
        gg = Gardener(args.config)
    else:
        gg = Gardener()
    if args.subparser_name == 'deploy': 
        gg.createGreengrass()
    elif args.subparser_name == 'listGroups':
        gg.getCurrentConfiguration()
    elif args.subparser_name == 'describeGroup':
        gg.getCurrentConfiguration(args.id)

        
    