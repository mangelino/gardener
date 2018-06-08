from .entity import EntityDefinition
import uuid
import json
from .logging import logError, logInfo, logRecycle, logSuccess, logDebug


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