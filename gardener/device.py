from .entity import EntityDefinition
from .thing import Thing
from itertools import chain
import json
from .logging import logError, logInfo, logRecycle, logSuccess, logDebug

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
