from .entity import EntityDefinition
import uuid
import json
from .logging import logError, logInfo, logRecycle, logSuccess, logDebug


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
            for v in self.config.Lambdas.values()]
    
    def getExistingDefinitions(self):
        return self.gg.list_function_definitions()['Definitions']

    def createEntityDefinition(self, name):
        return self.gg.create_function_definition(Name=name)

    def getEntityVersion(self, defId, verId):
        ver = self.gg.get_function_definition_version(FunctionDefinitionId=defId, FunctionDefinitionVersionId=verId)
        return ver['Definition']['Functions']

    def createEntityDefinitionVersion(self, defId, model):
        return self.gg.create_function_definition_version(FunctionDefinitionId=defId, Functions=model)