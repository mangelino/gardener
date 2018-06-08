#!/usr/local/bin/python
import json
import boto3
from itertools import chain
import uuid
import re
import sys
import argparse
from collections import OrderedDict

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


class Config:
    def __init__(self, file):
        f = open(file)
        dictionary = json.load(f)
        f.close()
        for k, v in dictionary.items():
            setattr(self, k, v)


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


class Gardener:
    _thingRegex = re.compile('thing:(?P<thing>\w+)')
    _shadowRegex = re.compile('shadow:(?P<thing>\w+):(?P<op>[\w/]+)')
    _lambdaRegex = re.compile('lambda:(?P<lambda>\w+)')

    def __init__(self, configfile='config.json'):
        self.config = Config(configfile)
        self.gg = boto3.client('greengrass', region_name=self.config.Region)
        self.iot = boto3.client('iot', region_name=self.config.Region)

    def dumpKeys(self, cert, privkey):
        print('Certificate PEM')
        print(cert)
        print('PrivateKey')
        print(privkey)

    def _createOrUpdatePolicy(self, policyName, policyDoc):
        policies = dict([(x['policyName'], x['policyArn']) for x in self.iot.list_policies()['policies']])

        if policyName + '_Policy' in policies.keys():
            currentPolicyDoc = self.iot.get_policy(policyName=policyName + '_Policy')['policyDocument']
            logInfo(currentPolicyDoc)
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

    def _createThing(self, name, policy):
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

    def _getFunctionDefinition(self, fn_definition):
        return [
            {
                "FunctionArn": v['arn'],
                "Id":str(uuid.uuid4()),
                "FunctionConfiguration": v['FunctionConfiguration']
            }
            for k, v in fn_definition.items()]

    def _getLoggersDefinition(self, logger_definition):
        return [
            {
                "Component": l['Component'],
                "Id": str(uuid.uuid4()),
                "Level": l['Level'],
                "Space": l['Space'],
                "Type": l['Type']
            }
            for l in logger_definition]

    def _getModelDefinition(self, things):
        return [
            {
                "ThingArn": t['thingArn'],
                "SyncShadow":t['syncShadow'],
                "CertificateArn":t['certArn'],
                "Id":str(uuid.uuid4())
            }
            for t in things]

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

    def _createCoreDefinition(self):
        """
        Create a new Core definition if it does not already exists.
        Compare LatestVersion with new model configuration to avoid creating identical versions
        """
        cdv = []
        coreDefinitionId = None
        if len(self.config.Cores.keys()) > 1:
            logError("Too many cores defined. Max number of cores is currently 1")
            return False
        name = self.config.Group['name'] + "_core_definition"
        cores = [dicSlice(x, ['Id', 'LatestVersion', 'LatestVersionArn']) for x in self.gg.list_core_definitions()[
                          'Definitions'] if 'Name' in x and x['Name'] == name]
        if len(cores) > 1:
            logError('More than 1 core with name {0} exists'.format(name))
            return False
        elif len(cores) == 1:
            coreDefinitionId = cores[0]['Id']
            # logRecycle('Core with name {0} aready exists with id {1}. Reusing it.'.format(name, coreDefinitionId))
            if 'LatestVersion' in cores[0]:
                cdv = self.gg.get_core_definition_version(
                    CoreDefinitionId=coreDefinitionId, CoreDefinitionVersionId=cores[0]['LatestVersion'])
                

        else:
            res = self.gg.create_core_definition(Name=name)
            coreDefinitionId = res['Id']
            logInfo('Create core definition {0}'.format(coreDefinitionId))
        coreKey = list(self.config.Cores.keys())[0]
        self._ggc = self._createThing(self.config.Cores[coreKey]['name'], self.config.Cores[coreKey]['policy'])
        modelDefinition = self._getModelDefinition(
            [{'thingArn': self._ggc['thingArn'], 'syncShadow': True, 'certArn':self._ggc['certArn']}])
        if len(cdv) > 0 and self.compareDefinitions(cdv['Definition']['Cores'], modelDefinition):
            logRecycle('Core version has not changed')
            self.coreDefinitionArn = cores[0]['LatestVersionArn']
        else:
            res = self.gg.create_core_definition_version(
                CoreDefinitionId=coreDefinitionId, Cores=modelDefinition)
            self.coreDefinitionArn = res['Arn']
            logSuccess('Created core definition version {0}'.format(
                self.coreDefinitionArn))
        return True

    def _createDeviceDefinition(self):
        """
        Create a new Device Definition if it does not already exists.
        Compare LatestVersion with new model configuration to avoid creating identical versions
        """
        deviceDefinitionId = None
        ddv = []
        name = "{0}_DeviceDefinition".format(self.config.Group['name'])
        devices = [dicSlice(x, ['Id', 'LatestVersion', 'LatestVersionArn']) for x in self.gg.list_device_definitions()[
                            'Definitions'] if 'Name' in x and x['Name'] == name]
        if len(devices) > 1:
            logError(
                'More than 1 device list with name {0} exists'.format(name))
            return False
        elif len(devices) == 1:
            
            deviceDefinitionId = devices[0]['Id']
            if 'LatestVersion' in devices[0]:
                ddv = self.gg.get_device_definition_version(
                    DeviceDefinitionId=deviceDefinitionId, DeviceDefinitionVersionId=devices[0]['LatestVersion'])
                #logRecycle('Current Device Definition version {0}'.format(devices[0]['LatestVersionArn']))
        else:
            res = self.gg.create_device_definition(Name=name)
            deviceDefinitionId = res['Id']
            logSuccess("Created device definition {0}".format(
                deviceDefinitionId))

        self._things = [dict(chain(self._createThing(v['name'], v['policy']).items(), v.items(), {
                             'id': k}.items())) for k, v in self.config.Things.items()]
        deviceModel = self._getModelDefinition(self._things)
        if len(ddv) > 0 and self.compareDefinitions(ddv['Definition']['Devices'], deviceModel):
            self.deviceDefinitionArn = devices[0]['LatestVersionArn']
            logRecycle('Device Version has not changed')
        else:
            res = self.gg.create_device_definition_version(
                DeviceDefinitionId=deviceDefinitionId, Devices=deviceModel)
            self.deviceDefinitionArn = res['Arn']
            logSuccess('Created device difinition version {0}'.format(
                self.deviceDefinitionArn))
        return True

    def _createLambdaDefinition(self):
        """
        Create a new Lambda Definition if it does not already exists.
        Compare LatestVersion with new model configuration to avoid creating identical versions
        """
        lambdaDefinitionId = None
        ldv=[]
        name = self.config.Group['name']+"_LambdaDefinition"
        lambdas = [dicSlice(x,['Id', 'LatestVersion', 'LatestVersionArn']) for x in self.gg.list_function_definitions()['Definitions'] if 'Name' in x and x['Name']==name]
        if len(lambdas)>1:
            logError('More than 1 lambda list exist with name {0}'.format(name))
            return False
        elif len(lambdas)==1:
            lambdaDefinitionId = lambdas[0]['Id']
            if 'LatestVersion' in lambdas[0]:
                ldv = self.gg.get_function_definition_version(FunctionDefinitionId=lambdaDefinitionId, FunctionDefinitionVersionId=lambdas[0]['LatestVersion'])
                #logRecycle('Current Lambda Definition version {0}'.format(lambdas[0]['LatestVersionArn']))
        else:
            res = self.gg.create_function_definition(Name=name)
            lambdaDefinitionId = res['Id']
            logSuccess('Created lambda definition {0}'.format(lambdaDefinitionId))
       

        lambdaModel = self._getFunctionDefinition(self.config.Lambdas)
        if len(ldv)>0 and self.compareDefinitions(ldv['Definition']['Functions'], lambdaModel):
            self.lambdaDefinitionArn = lambdas[0]['LatestVersionArn']
            logRecycle('Function Version has not changed')
        else:
            res = self.gg.create_function_definition_version(FunctionDefinitionId=lambdaDefinitionId, Functions=lambdaModel)
            self.lambdaDefinitionArn = res['Arn']
            logSuccess('Creates lambda definition version {0}'.format(self.lambdaDefinitionArn))
        return True
    
    def _createSubscriptionDefinition(self):
        """
        Create a new Subscription Definition if it does not already exists.
        Compare LatestVersion with new model configuration to avoid creating identical versions
        """
        subscriptionId = None
        sdv=[]
        name = self.config.Group['name']+"_SubscriptionDefinition"
        subs = [dicSlice(x,['Id', 'LatestVersion', 'LatestVersionArn']) for x in self.gg.list_subscription_definitions()['Definitions'] if 'Name' in x and x['Name']==name]
        if len(subs) > 1:
            logError('More than 1 subscription lists with name {0} exists'.format(name))
            return False
        elif len(subs)==1:
            subscriptionId = subs[0]['Id']
            if 'LatestVersion' in subs[0]:
                sdv = self.gg.get_subscription_definition_version(SubscriptionDefinitionId=subscriptionId, SubscriptionDefinitionVersionId=subs[0]['LatestVersion'])
                #logRecycle('Current Subscription Definition version {0}'.format(subs[0]['LatestVersionArn']))
        else:
            res = self.gg.create_subscription_definition(Name=name)
            subscriptionId = res['Id']
            logSuccess('Created subscription definition {0}'.format(subscriptionId))
        try:
            subsModel = self._getSubscriptionModel(self.config.Routes, self._things, self.config.Lambdas)
        except NameError as e:
            logError(e)
            return False
        if len(sdv)>0 and self.compareDefinitions(sdv['Definition']['Subscriptions'], subsModel):
            logRecycle('Subscritpion Version has not changed')
            self.subscriptionDefinitionArn = subs[0]['LatestVersionArn']
        else:
            print(subsModel)
            res = self.gg.create_subscription_definition_version(SubscriptionDefinitionId = subscriptionId, Subscriptions = subsModel)
            self.subscriptionDefinitionArn=res['Arn']
            logSuccess('Created subscription definition version {0}'.format(self.subscriptionDefinitionArn))
        return True

    def _createLoggingDefinition(self):
        """
        Create a new Logging Definition if it does not already exists.
        Compare LatestVersion with new model configuration to avoid creating identical versions
        """
        loggerId = None
        ldv = []
        logger = [dicSlice(x,['Id', 'LatestVersion', 'LatestVersionArn']) for x in self.gg.list_logger_definitions()['Definitions'] if 'Name' in x and x['Name']==self.config.Group['name']+"_Logging"]
        if len(logger)>1:
            logError ('More than 1 logging list with same name {0} already exists. Rename or delete other groups to continue.'.format(self.config.Group['name']+'_Logging'))
            return False
        elif len(logger) == 1:
            loggerId = logger[0]['Id']
            if 'LatestVersion' in logger[0]:
                ldv = self.gg.get_logger_definition_version(LoggerDefinitionId=loggerId, LoggerDefinitionVersionId=logger[0]['LatestVersion'])
                #logRecycle('Current Loggers Definition version {0}'.format(logger[0]['LatestVersionArn']))
        else:
            res = self.gg.create_logger_definition(Name=self.config.Group['name']+"_Logging")
            loggerId = res['Id']
            logSuccess('Created logger definition {0}'.format(loggerId))
        loggerModel = self._getLoggersDefinition(self.config.Loggers)
        
        if len(ldv) > 0:
            for l in ldv['Definition']['Loggers']:
                l['Space'] = str(l['Space'])
        
        if len(ldv)>0 and self.compareDefinitions(ldv['Definition']['Loggers'], loggerModel):
            logRecycle('Logger Version has not changed')
            self.loggerDefinitionArn = logger[0]['LatestVersionArn']
        else: 
            res = self.gg.create_logger_definition_version(LoggerDefinitionId=loggerId, Loggers=loggerModel)
            self.loggerDefinitionArn = res['Arn']
            logSuccess('Created logger defintion version {0}'.format(self.loggerDefinitionArn))
        return True

    def compareGroupVersion(self,gdv):
        logRecycle("""--core-definition-version-arn {0}
        --device-definition-version-arn {1}
        --function-definition-version-arn {2}
        --logger-definition-version-arn {3}
        --subscription-definition-version-arn {4}""".format(self.coreDefinitionArn,self.deviceDefinitionArn,self.lambdaDefinitionArn,self.loggerDefinitionArn,self.subscriptionDefinitionArn))
        return (gdv['CoreDefinitionVersionArn'] == self.coreDefinitionArn and
            gdv['DeviceDefinitionVersionArn'] == self.deviceDefinitionArn and
            gdv['FunctionDefinitionVersionArn'] == self.lambdaDefinitionArn and
            gdv['LoggerDefinitionVersionArn'] == self.loggerDefinitionArn and
            gdv['SubscriptionDefinitionVersionArn'] == self.subscriptionDefinitionArn)

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
            res = self.gg.create_group_version(GroupId=self.groupId, CoreDefinitionVersionArn=self.coreDefinitionArn, DeviceDefinitionVersionArn=self.deviceDefinitionArn, 
            FunctionDefinitionVersionArn=self.lambdaDefinitionArn, LoggerDefinitionVersionArn=self.loggerDefinitionArn, SubscriptionDefinitionVersionArn=self.subscriptionDefinitionArn)
            self.groupVersion = res['Version']
            logSuccess('Created group version {0} {1}'.format(res['Arn'], res['Version']))       
        return True
    
    def _createGGGroupWithCoreOnly(self):
        groups = [x['Id'] for x in self.gg.list_groups()['Groups'] if 'Name' in x and x['Name']==self.Config.Group]
        if len(groups)>1:
            logError('More than 1 group with same name {0} already exists. Rename or delete other groups to continue.'.format(self.Config.Group))
            return False
        elif len(groups) == 1:
            # logRecycle ('Group {0} already exists with id {1}. Updating it'.format(self.Config.Group, groups[0]))
            self.groupId = groups[0]
        else:
            res = self.gg.create_group(Name=self.config.Group['name'])
            self.groupId = res['Id']
            logSuccess('Created group {0} with id {1}'.format(self.config.Group['name'], self.groupId))
        
        res = self.gg.create_group_version(GroupId=self.groupId, CoreDefinitionVersionId=self.coreDefinitionArn)
        self.groupVersion = res['Version']
        logSuccess('Created group version {0} {1}'.format(res['Arn'], res['Version']))       
        return True
    
    def _createDeployment(self):
        res = self.gg.create_deployment(DeploymentType='NewDeployment', GroupId=self.groupId, GroupVersion=self.groupVersion)
        logSuccess('Created deployment {0}'.format(res))
        return True

    def createGreengrass(self):
        if self._createCoreDefinition() and self._createDeviceDefinition() and self._createLambdaDefinition() and self._createLoggingDefinition() and self._createSubscriptionDefinition() and self._createGGGroup():
            if self.config.Group['deploy']:
                if self._createDeployment():
                    print('Execute the followinf command on your Core')
                    print('''sudo sed -e 's/THING_ARN_HERE/{0}' /greengrass/configuration/config.json > /greengrass/configuration/config.json'''.format(self._ggc['thingArn']))
                else:
                    print ('Something went wrong while deploying your Greengrass configuration')
            else:
                logSuccess('Greengrass has been configured but not deployed. Execute this command to deploy or use the console.')
                print('aws greengrass create-deployment --deployment-type "NewDeployment" --group-id {0} --group-version {1} --region {2}'.format(self.groupId, self.groupVersion, self.config.Region))
        else:
            print("Something went wrong while creating the Greengrass configuration")

    def createGroupAndCore(self):
        if self._createCoreDefinition() and self._createGGGroupWithCoreOnly():
            print('Greengrass Group and Core created')
        else:
            print("Something went wrong while creating the Greengrass configuration")
        
    def getLatestDeploymentStatus(self, groupName):
        res = gg.list_groups()
        group = [g for g in res['Groups'] if g['Name'] == groupName]
        if len(group) == 0:
            logError("No groups matching {0}".format(groupName))
            return False
        res = gg.list_deployments(GroupId=group[0]['Id'])
        deployments = res['Deployments']
        if len(deployments) == 0:
            logError("No deployments found for group {0}".format(groupName))
            return False
        deployments = sorted(deployments, key=lambda x: x["CreatedAt"], reverse=True)
        deploymentId = deployments[0]['Id']
        res = gg.get_deployment_status(DeploymentId = deploymentId, GroupId=group[0]['Id'])
        print("Latest deployment for group {0} is {1}".format(groupName, res['DeploymentStatus']))

    def getCurrentConfiguration(self):
        groups = self.gg.list_groups()['Groups']
        jsonPP(groups)
        coreDefinitions = self.gg.list_core_definitions()['Definitions']
        jsonPP(coreDefinitions)
        for cd in coreDefinitions:
            coreDefVersion = self.gg.get_core_definition_version(CoreDefinitionId=cd['Id'], CoreDefinitionVersionId=cd['LatestVersion'])
            coreDefVersion.pop('ResponseMetadata')
            jsonPP(coreDefVersion)
        functionDefinitions= self.gg.list_function_definitions()['Definitions']
        jsonPP(functionDefinitions) 
        for fd in functionDefinitions:
            funcDefVer = self.gg.get_function_definition_version(FunctionDefinitionId=fd['Id'], FunctionDefinitionVersionId=fd['LatestVersion'])
            funcDefVer.pop("ResponseMetadata")
            jsonPP(funcDefVer)


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
                self.ggcms.delete_logging_definition(LoggingId=x)
            except:
                print('Unable to delete')


        
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Greengrass Gardener')
    parser.add_argument('--config')
    subparsers = parser.add_subparsers(help='sub-command help', dest='subparser_name')

    parser_deploy = subparsers.add_parser('deploy', help='deploy help')
    parser_deploy.add_argument('--config')
    parser_ls = subparsers.add_parser('ls', help='ls help')

    args = parser.parse_args()
    if args.config:
        gg = Gardener(args.config)
    else:
        gg = Gardener()
    if args.subparser_name == 'deploy': 
        gg.createGreengrass()
    elif args.subparser_name == 'ls':
        gg.getCurrentConfiguration()
        
    