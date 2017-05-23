
import json
from gg_config import config
import boto3
from itertools import chain
import uuid
import re
import sys

class Greengrass:
    _thingRegex = re.compile('thing:(?P<thing>\w+)')
    _shadowRegex = re.compile('shadow:(?P<thing>\w+):(?P<op>[\w/]+)')
    _lambdaRegex = re.compile('lambda:(?P<lambda>\w+)')
    
    def __init__(self, config):
        self.config = config
        self.ggcms = boto3.client('ggcms', region_name='us-west-2')
        self.iot = boto3.client('iot', region_name='us-west-2')
        self.ggcds = boto3.client('ggcds', region_name='us-west-2')

    def _createThing(self, name):
        res = self.iot.create_thing(thingName = name)
        thingArn = res['thingArn']
        print('Created thing {0} with ARN {1}'.format(name, thingArn))
        res = self.iot.create_keys_and_certificate(setAsActive=True)
        print('Created certificate and keys')
        certArn = res['certificateArn']
        print('\tARN: {0}'.format(certArn))
        print('Certificate PEM')
        print(res['certificatePem'])
        print('PrivateKey')
        print(res['keyPair']['PrivateKey'])
        policies = dict([(x['policyName'],x['policyArn']) for x in self.iot.list_policies()['policies']])
        if name+'_Policy' in policies.keys():    
            print('Policy {0} already exists with arn {1}.\nReusing it as-is'.format(name+'_Policy', policies[name+'_Policy']))

        else:
            res = self.iot.create_policy(policyName=name+"_Policy", policyDocument='{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["iot:*","greengrass:*"],"Resource":["*"]}]}')
            print('Created policy {0}'.format(res['policyArn']))
        res = self.iot.attach_principal_policy(policyName=name+"_Policy", principal=certArn)
        print('Attached policy to certificate')
        res = self.iot.attach_thing_principal(thingName=name, principal=certArn)
        print('Attached certificate to thing')
        return {'thingArn':thingArn, 'certArn': certArn}


    def _getFunctionList(self, fn_list):
        return [{"FunctionArn":x['arn']} for x in fn_list]


    def _getModelList(self, things):
        return [{"ThingArn":t['thingArn'], "SyncShadow":t['syncShadow'], "CertArn":t['certArn']} for t in things]


    def _getSubscriptionModel(self, subs, things):
        def _getThingArn(id, things):
            for t in things:
                if t['id'] == id:
                    return t['thingArn']


        def _getLambdaArn(id, lambdas):
            for l in lambdas:
                if l['id'] == id:
                    return l['arn']


        def _checkThing(d, element):
            #print ('Thing'+str(d))
            m = self._thingRegex.match(d[element])
            if m:
                d[element] = _getThingArn(m.group('thing'), things)


        def _checkLambda(d, element):
            #print ('Lambda'+str(d))
            m = self._lambdaRegex.match(d[element])
            if m:
                d[element] = _getLambdaArn(m.group('lambda'), self._config.Lambdas)


        def _getThingName(id):
            for t in things:
                if t['id'] == id:
                    return t['name']


        def _checkSubject(d):
            #print('Subject'+str(d))
            m = self._shadowRegex.match(d['Subject'])
            if m:
                d['Subject'] = '$aws/things/{0}/shadow{1}'.format(self._getThingName(m.group('thing'), things), m.group('op'))


        def _buildSubscriptionElement(d):
            _checkThing(d, 'Source')
            _checkThing(d, 'Target')
            _checkLambda(d, 'Source')
            _checkLambda(d, 'Target')
            _checkSubject(d)
            return dict(chain(d.items(), {"Id":str(uuid.uuid4())}.items()))


        return [_buildSubscriptionElement(m) for m in subs]

    def _createCoreList(self):
        coreListId=None
        name = config.Group+"_core_list"
        cores = [x['Id'] for x in self.ggcms.list_core_lists()['DefinitionInformationList'] if 'Name' in x and x['Name']==name]
        if len(cores)>1:
            print('More than 1 core with name {0} exists'.format(name))
            return False
        elif len(cores) == 1:
            coreListId = cores[0]
        else:
            res = self.ggcms.create_core_list(Name=name)
            coreListId = res['Id']
            print('Create core list {0}'.format(coreListId))

        self._ggc = self._createThing(config.Core)
        modelList = self._getModelList([{'thingArn':self._ggc['thingArn'], 'syncShadow': True, 'certArn':self._ggc['certArn']}])

        res = self.ggcms.create_core_list_version(CoreId=coreListId, coresModelList=modelList)
        self.coreListArn = res['Arn']
        print('Created core list version {0}'.format(self.coreListArn))
        return True

    def _createDeviceList(self):
        deviceListId = None
        name = "{0}_DeviceList".format(self.config.Group)
        devices = [x['Id'] for x in self.ggcms.list_device_lists()['DefinitionInformationList'] if 'Name' in x and x['Name']==name]
        if len(devices)>1:
            print('More than 1 device list with name {0} exists'.format(name))
            return False
        elif len(devices)==1:
            deviceListId=devices[0]
        else:           
            res = self.ggcms.create_device_list(Name=name)
            deviceListId = res['Id']
            print("Created device list {0}".format(deviceListId))

        self._things = [dict(chain(self._createThing(t['name']).items(), t.items())) for t in self.config.Things]
        res = self.ggcms.create_device_list_version(DeviceId=deviceListId, devicesModelList=self._getModelList(self._things))
        self.deviceListArn = res['Arn']
        print('Create device list version {0}'.format(self.deviceListArn))
        return True

    def _createLambdaList(self):
        lambdaListId = None
        name = self.config.Group+"_LambdaList"
        lambdas = [x['Id'] for x in self.ggcms.list_subscription_lists()['DefinitionInformationList'] if 'Name' in x and x['Name']==name]
        if len(lambdas)>1:
            print('More than 1 lambda list exist with name {0}'.format(name))
            return False
        elif len(lambdas)==1:
            lambdaListId = lambdas[0]
        else:
            res = self.ggcms.create_lambda_list(Name=name)
            lambdaListId = res['Id']
            print('Created lambda list {0}'.format(lambdaListId))

        res = self.ggcms.create_lambda_list_version(LambdasId=lambdaListId, lambdaModelsList=self._getFunctionList(self.config.Lambdas))
        self.lambdaListArn = res['Arn']
        print('Creates lambda list version {0}'.format(self.lambdaListArn))
        return True
    
    def _createSubscriptionList(self):
        subscriptionId = None
        name = self.config.Group+"_SubscriptionList"
        subs = [x['Id'] for x in self.ggcms.list_subscription_lists()['DefinitionInformationList'] if 'Name' in x and x['Name']==name]
        if len(subs) > 1:
            print('More than 1 subscription lists with name {0} exists'.format(name))
            return False
        elif len(sub)==1:
            subscriptionId = subs[0]
            print('Subscription list {0} already exists with id {1}. Reusing it.'.format(name, subscriptionId))
        else:
            res = self.ggcms.create_subscription_list(Name=name)
            subscriptionId = res['Id']
            print('Created subscription list {0}'.format(subscriptionId))

        res = self.ggcms.create_subscription_list_version(SubscriptionsId = subscriptionId, subscriptionModelList=self._getSubscriptionModel(self.config.Routes, self._things))
        self.subscriptionListArn=res['Arn']
        print('Created subscription list version {0}'.format(self.subscriptionListArn))
        return True

    def _createLoggingList(self):
        loggingId = None
        logging = [x['Id'] for x in self.ggcms.list_logging_list()['DefinitionInformationList'] if 'Name' in x and x['Name']==self.Config.Group+"_Logging"]
        if len(logging)>1:
            print ('More than 1 logging list with same name {0} already exists. Rename or delete other groups to continue.'.format(self.Config.Group+'_Logging'))
            return False
        elif len(logging) == 1:
            print('Logging list {0} already exists with id {1}. Updating it'.format(self.Config.Group+'_Logging', logging[0]))
            loggingId = groups[0]
        else:
            res = self.ggcms.create_logging_list(Name=self.config.Group+"_Logging")
            loggingId = res['Id']
            print('Created logging list {0}'.format(loggingId))
        
        res = self.ggcms.create_logging_list_version(LoggingId=loggingId, loggingModelList=[{"Component":"GreengrassSystem","Level":"DEBUG","Space":"5M","Type": "FileSystem"},{"Component":"Lambda","Level":"DEBUG","Space":"5M","Type": "FileSystem"}])
        self.loggingListArn = res['Arn']
        print('Created logging list version {0}'.format(self.loggingListArn))
        return True

    def _createGGGroup(self):
        groups = [x['Id'] for x in self.ggcms.list_groups()['DefinitionInformationList'] if 'Name' in x and x['Name']==self.Config.Group]
        if len(groups)>1:
            print('More than 1 group with same name {0} already exists. Rename or delete other groups to continue.'.format(self.Config.Group))
            return False
        elif len(groups) == 1:
            print ('Group {0} already exists with id {1}. Updating it'.format(self.Config.Group, groups[0]))
            self.groupId = groups[0]
        else:
            res = self.ggcms.create_group(Name=self.config.Group)
            self.groupId = res['Id']
            print('Created group {0} with id {1}'.format(self.config.Group, self.groupId))
        
        res = self.ggcms.create_group_version(GroupId=self.groupId, Cores={'Ref': self.coreListArn}, Devices={'Ref':self.deviceListArn}, 
            Lambdas={'Ref': self.lambdaListArn}, Logging={'Ref':self.loggingListArn}, Subscriptions={'Ref':self.subscriptionListArn}, Configuration={'GroupCACert':self._ggc['certArn']})
        self.groupVersion = res['Version']
        print('Created group version {0} {1}'.format(res['Arn'], res['Version']))       
        return True
    
    def _createDeployment(self):
        res = self.ggcds.create_deployment(DeploymentType='NewDeployment', GroupId=self.groupId, GroupVersion=self.groupVersion)
        print('Created deployment {0}'.format(res))
        return True

    def createGreenGrass(self):
        if self._createCoreList() and self._createDeviceList() and self._createLambdaList() and self._createLoggingList() and self._createSubscriptionList() and self._createGGGroup() and self._createDeployment():
            print('Execute the followinf command on your Core')
            print('''sudo sed -e 's/THING_ARN_HERE/{0}' /greengrass/configuration/config.json > /greengrass/configuration/config.json'''.format(self._ggc['thingArn']))
        else:
            print("Something went wrong")

    def getCurrentConfiguration(self):
        print(json.dumps(self.ggcms.list_groups()['DefinitionInformationList'], indent=2))
        print(json.dumps(self.ggcms.list_core_lists()['DefinitionInformationList'], indent=2))

    def cleanUpAll(self):
        groupIds = [x['Id'] for x in self.ggcms.list_groups()['DefinitionInformationList']]
        coreListIds = [x['Id'] for x in self.ggcms.list_core_lists()['DefinitionInformationList']]
        deviceListIds = [x['Id'] for x in self.ggcms.list_device_lists()['DefinitionInformationList']]
        lambdaListIds = [x['Id'] for x in self.ggcms.list_lambda_lists()['DefinitionInformationList']]
        subscriptionListIds = [x['Id'] for x in self.ggcms.list_subscription_lists()['DefinitionInformationList']]
        loggingListIds = [x['Id'] for x in self.ggcms.list_logging_lists()['DefinitionInformationList']]
        print('Cleaning up groups...')
        for x in groupIds:
            try:
                print(x)
                self.ggcms.delete_group(GroupId=x)
            except:
                print('Unable to delete')
        print('Cleaning up cores...')
        for x in coreListIds:
            try:
                print(x)
                self.ggcms.delete_core_list(CoreId=x)
            except:
                print('Unable to delete')
        print('Cleaning up devices...')
        for x in deviceListIds:
            try:
                print(x)
                self.ggcms.delete_device_list(DeviceId=x)
            except:
                print('Unable to delete')
        print('Cleaning up lambdas...')
        for x in lambdaListIds:
            try:
                print(x)
                self.ggcms.delete_lambda_list(LambdaId=x)
            except:
                print('Unable to delete')
        print('Cleaning up subscriptions...')
        for x in subscriptionListIds:
            try:
                print(x)
                self.ggcms.delete_subscription_list(SubscritpionId=x)
            except:
                print('Unable to delete')
        print('Cleaning up logging...')
        for x in loggingListIds:
            try:
                print(x)
                seld.ggcms.delete_logging_list(LoggingId=x)
            except:
                print('Unable to delete')


        

