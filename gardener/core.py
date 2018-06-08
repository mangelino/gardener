from gardener.entity import EntityDefinition
from gardener.thing import Thing
from itertools import chain
import json
from gardener.logging import logError, logInfo, logRecycle, logSuccess, logDebug

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
        self.thingName = self.config.Cores[coreKey]['name']
        self.coreThing = thing.createThing(self.thingName, self.config.Cores[coreKey]['policy'])
        things = [dict(chain(self.coreThing.items(), v.items(), {'id': k}.items())) for k,v in self.config.Cores.items()]
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