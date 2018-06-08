from .logging import logError, logInfo, logRecycle, logSuccess
from .utils import dicSlice, hashDict, compareDict 

class EntityDefinition: 
    def __init__(self, gg, config):
        self.gg = gg
        self.entityName = "entity"
        self.config = config

    def getPostfix(self):
        raise NotImplementedError( "Should have implemented this" )

    def getExistingDefinitions(self):
        raise NotImplementedError( "Should have implemented this" )

    def getEntityVersion(self, defId, verId):
        raise NotImplementedError( "Should have implemented this" )

    def getModelDefinition(self):
        raise NotImplementedError( "Should have implemented this" )

    def createEntityDefinition(self, name):
        raise NotImplementedError( "Should have implemented this" )

    def createEntityDefinitionVersion(self, defId, model):
        raise NotImplementedError( "Should have implemented this" )

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
        if len(version) and compareDict(version, modelDefinition):
            logRecycle('{0} version has not changed'.format(self.entityName))
            self.arn = definitions[0]['LatestVersionArn']
        else:
            res = self.createEntityDefinitionVersion(entityDefinitionId, modelDefinition)
            self.arn = res['Arn']
            logSuccess('Created {0} definition version {1}'.format(self.entityName, self.arn))
        return True