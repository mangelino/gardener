from gardener.entity import EntityDefinition
import uuid
import json
from itertools import chain
from gardener.logging import logError, logInfo, logRecycle, logSuccess, logDebug
import re


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