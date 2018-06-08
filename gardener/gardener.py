import json
import boto3

import uuid
import re
from gardener.config import Config
from gardener.utils import jsonPP, dicSlice
from gardener.logging import logError, logInfo, logRecycle, logSuccess, logDebug
from gardener.globals import CERT_POSTFIX, KEY_POSTFIX
from gardener.core import CoreDefinition
from gardener.function import FunctionDefinition
from gardener.device import DeviceDefinition
from gardener.logger import LoggerDefinition
from gardener.subscription import SubscriptionDefinition
from gardener.group import GroupDefinition

class Gardener:
    def __init__(self, configfile='config.json'):
        self.config = Config(configfile)
        self.gg = boto3.client('greengrass', region_name=self.config.Region)
    
    def _createDeployment(self):
        res = self.gg.create_deployment(DeploymentType='NewDeployment', GroupId=self.group.groupId, GroupVersionId=self.group.groupVersion)
        res.pop('ResponseMetadata')
        logSuccess('Created deployment {0}'.format(res))
        return True

    def createGreengrass(self):
        self.core = CoreDefinition(self.gg, self.config)
        self.devices = DeviceDefinition(self.gg, self.config)
        self.functions = FunctionDefinition(self.gg, self.config)
        self.subscriptions = SubscriptionDefinition(self.gg, self.config, self.devices)
        self.loggers = LoggerDefinition(self.gg, self.config)
        self.group = GroupDefinition(self.gg, self.config, self.core, self.devices, self.functions, self.loggers, self.subscriptions)

        if self.core.create() and self.devices.create() and self.functions.create() and self.loggers.create() and self.subscriptions.create() and self.group.create():
            configFileContent = '''
{
    "coreThing": {
        "caPath": "root.ca.pem",
        "certPath": "%s",
        "keyPath": "%s",
        "thingArn": "%s",
        "iotHost": "%s.iot.%s.amazonaws.com",
        "ggHost": "greengrass.iot.%s.amazonaws.com"
    },
    "runtime": {
        "cgroup": {
            "useSystemd": "no"
        }
    },
    "managedRespawn": false
}
            ''' % (self.core.thingName+CERT_POSTFIX, self.core.thingName+KEY_POSTFIX, self.core.coreThing['thingArn'], 'xxxx',self.config.Region, self.config.Region )
            if self.config.Group['deploy']:
                if not self._createDeployment():
                    raise RuntimeError("Deployment could not be created")
            return configFileContent
        else:
            raise RuntimeError("Something went wrong while creating the Greengrass configuration")