
from gardener.logging import logError, logInfo, logRecycle, logSuccess, logDebug
from gardener.utils import dicSlice

class GroupDefinition:
    def __init__(self, gg, config, core, devices, functions, loggers, subscriptions):
        self.gg = gg
        self.config = config
        self.core = core
        self.devices = devices
        self.functions = functions
        self.loggers = loggers
        self.subscriptions = subscriptions
    
    def create(self):
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

    def compareGroupVersion(self, gdv):
        # logRecycle("""--core-definition-version-arn {0}
        # --device-definition-version-arn {1}
        # --function-definition-version-arn {2}
        # --logger-definition-version-arn {3}
        # --subscription-definition-version-arn {4}""".format(self.core.arn,self.devices.arn,self.functions.arn,self.loggers.arn,self.subscriptions.arn))
        return (gdv['CoreDefinitionVersionArn'] == self.core.arn and
            gdv['DeviceDefinitionVersionArn'] == self.devices.arn and
            gdv['FunctionDefinitionVersionArn'] == self.functions.arn and
            gdv['LoggerDefinitionVersionArn'] == self.loggers.arn and
            gdv['SubscriptionDefinitionVersionArn'] == self.subscriptions.arn)